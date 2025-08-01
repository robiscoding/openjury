from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from openjury.config import JuryConfig, ResponseCandidate
from openjury.juror import Juror, JurorException
from openjury.logger import logger
from openjury.output_format import Verdict, VerdictFormatter
from openjury.voting import JurorEvaluation, VotingAggregator, VotingMethod


class OpenJuryInitializationError(Exception):
    pass


class OpenJuryEvaluationError(Exception):
    pass


class OpenJury:
    def __init__(
        self,
        config: JuryConfig,
        parallel_execution: bool = True,
    ):
        self.config = config
        self.parallel_execution = parallel_execution
        self.jurors = []

        for cfg in config.jurors:
            try:
                juror = Juror(cfg)
                self.jurors.append(juror)
                logger.info(f"Initialized juror: {juror.name}")
            except Exception as e:
                logger.error(f"Failed to initialize juror {cfg.name}: {e}")
                raise OpenJuryInitializationError(
                    f"Failed to initialize juror {cfg.name}: {e}"
                )

        if not self.jurors:
            raise OpenJuryInitializationError("No jurors were successfully initialized")

        logger.info(f"OpenJury initialized with {len(self.jurors)} jurors")

    def __repr__(self) -> str:
        return f"OpenJury(name='{self.config.name}', jurors={len(self.jurors)}, criteria={len(self.config.criteria)})"

    def _evaluate_with_juror(
        self, juror: Juror, prompt: str, responses: List[ResponseCandidate]
    ) -> tuple[Juror, Dict[str, Dict[str, float]], Dict[str, Dict[str, str]]]:

        try:
            scores, explanations = juror.evaluate(
                prompt=prompt,
                responses=responses,
                criteria=self.config.criteria,
                max_retries=self.config.max_retries,
            )
            return juror, scores, explanations
        except JurorException as e:
            logger.error(f"Juror {juror.name} failed: {e}")
            raise

    def evaluate(
        self,
        prompt: str,
        responses: List[ResponseCandidate],
        response_ids: Optional[List[str]] = None,
    ) -> Verdict:

        if not responses:
            raise OpenJuryEvaluationError("No responses provided for evaluation")

        if len(responses) < 2:
            logger.warning("Only one response provided - comparison will be limited")

        response_mapping = {}

        for response in responses:
            response_mapping[response.id] = response.content

        if response_ids is None:
            response_ids = [response.id for response in responses]
        elif len(response_ids) != len(responses):
            raise OpenJuryEvaluationError(
                "Number of response_ids must match number of responses"
            )
        else:
            response_mapping = {}
            for i, response in enumerate(responses):
                response_mapping[response_ids[i]] = response.content

        logger.info(
            f"Starting evaluation with {len(self.jurors)} jurors for {len(responses)} responses"
        )

        juror_evaluations = []
        all_explanations = {}
        if self.parallel_execution and len(self.jurors) > 1:
            with ThreadPoolExecutor(max_workers=min(len(self.jurors), 10)) as executor:
                future_to_juror = {
                    executor.submit(
                        self._evaluate_with_juror, juror, prompt, responses
                    ): juror
                    for juror in self.jurors
                }
                successful_evaluations = 0
                for future in as_completed(future_to_juror):
                    juror = future_to_juror[future]
                    try:
                        juror_obj, scores, explanations = future.result()
                        evaluation = JurorEvaluation(
                            juror_name=juror_obj.name,
                            response_scores=scores,
                            juror_weight=juror_obj.config.weight,
                        )
                        juror_evaluations.append(evaluation)
                        all_explanations[juror_obj.name] = explanations
                        successful_evaluations += 1
                        logger.info(f"Juror {juror_obj.name} completed evaluation")
                    except Exception as e:
                        logger.error(f"Juror {juror.name} failed: {e}")
                        continue
        else:
            successful_evaluations = 0
            for juror in self.jurors:
                try:
                    juror_obj, scores, explanations = self._evaluate_with_juror(
                        juror, prompt, responses
                    )
                    evaluation = JurorEvaluation(
                        juror_name=juror_obj.name,
                        response_scores=scores,
                        juror_weight=juror_obj.config.weight,
                    )
                    juror_evaluations.append(evaluation)
                    all_explanations[juror_obj.name] = explanations
                    successful_evaluations += 1
                    logger.info(f"Juror {juror_obj.name} completed evaluation")
                except Exception as e:
                    logger.error(f"Juror {juror.name} failed: {e}")
                    continue

        if successful_evaluations == 0:
            raise OpenJuryEvaluationError("All jurors failed to complete evaluation")

        if successful_evaluations < len(self.jurors):
            logger.warning(
                f"Only {successful_evaluations}/{len(self.jurors)} jurors completed successfully"
            )

        try:
            if self.config.voting_method == VotingMethod.CUSTOM:
                custom_function_name = getattr(
                    self.config, "custom_voting_function", None
                )
                if not custom_function_name:
                    raise OpenJuryEvaluationError(
                        "Custom voting method selected but no custom_voting_function specified in config"
                    )

                voting_result = VotingAggregator.aggregate(
                    evaluations=juror_evaluations,
                    method=VotingMethod.CUSTOM,
                    custom_function_name=custom_function_name,
                )
                logger.info(f"Custom voting completed: winner = {voting_result.winner}")
            else:
                voting_result = VotingAggregator.aggregate(
                    evaluations=juror_evaluations, method=self.config.voting_method
                )
                logger.info(f"Voting completed: winner = {voting_result.winner}")
        except Exception as e:
            logger.error(f"Voting aggregation failed: {e}")
            raise OpenJuryEvaluationError(f"Failed to aggregate votes: {e}")

        try:
            verdict = VerdictFormatter.create_verdict(
                jury_config=self.config,
                original_prompt=prompt,
                responses=response_mapping,
                juror_evaluations=juror_evaluations,
                voting_result=voting_result,
                explanations=all_explanations,
            )

            logger.info(
                f"Verdict created: {verdict.final_verdict.winner} wins with {verdict.final_verdict.confidence:.2f} confidence"
            )
            return verdict

        except Exception as e:
            logger.error(f"Failed to create verdict: {e}")
            raise OpenJuryEvaluationError(f"Failed to create verdict: {e}")

    def get_summary(self) -> Dict[str, any]:
        return {
            "name": self.config.name,
            "description": self.config.description,
            "num_jurors": len(self.jurors),
            "num_criteria": len(self.config.criteria),
            "voting_method": self.config.voting_method.value,
            "jurors": [
                {
                    "name": juror.name,
                    "model": juror.config.model_name,
                    "weight": juror.config.weight,
                }
                for juror in self.jurors
            ],
            "criteria": [
                {
                    "name": criterion.name,
                    "description": criterion.description,
                    "weight": criterion.weight,
                    "max_score": criterion.max_score,
                }
                for criterion in self.config.criteria
            ],
        }
