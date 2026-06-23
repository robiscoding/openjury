from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from openjury.config import AgentResponse, JuryConfig
from openjury.endpoint_fetcher import AgentEndpoint, fetch_all_responses
from openjury.juror import Juror, JurorException
from openjury.logger import logger
from openjury.output_format import (
    AgentEvalResult,
    CriterionEvaluation,
    ResultFormatter,
    TrialResult,
)
from openjury.scoring import JurorScore, ScoreAggregator


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
        self.jurors: List[Juror] = []

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
        return (
            f"OpenJury(name='{self.config.name}', "
            f"jurors={len(self.jurors)}, "
            f"criteria={len(self.config.criteria)})"
        )

    def _score_with_juror(
        self,
        juror: Juror,
        prompt: str,
        response: AgentResponse,
        references: Optional[str],
        case_rules: Optional[str],
    ) -> JurorScore:
        return juror.evaluate(
            prompt=prompt,
            response=response,
            criteria=self.config.criteria,
            score_scale=self.config.score_scale,
            max_retries=self.config.max_retries,
            evaluation_template=self.config.evaluation_template,
            references=references,
            case_rules=case_rules,
        )

    def _run_jurors(
        self,
        prompt: str,
        response: AgentResponse,
        references: Optional[str],
        case_rules: Optional[str],
    ) -> List[JurorScore]:
        """Run all jurors against a single response; skip failures in parallel mode."""
        juror_scores: List[JurorScore] = []

        if self.parallel_execution and len(self.jurors) > 1:
            with ThreadPoolExecutor(max_workers=min(len(self.jurors), 10)) as executor:
                future_map = {
                    executor.submit(
                        self._score_with_juror,
                        juror,
                        prompt,
                        response,
                        references,
                        case_rules,
                    ): juror
                    for juror in self.jurors
                }
                for future in as_completed(future_map):
                    juror = future_map[future]
                    try:
                        juror_scores.append(future.result())
                        logger.info(f"Juror {juror.name} completed scoring")
                    except Exception as e:
                        logger.error(f"Juror {juror.name} failed: {e}")
        else:
            for juror in self.jurors:
                try:
                    juror_scores.append(
                        self._score_with_juror(
                            juror, prompt, response, references, case_rules
                        )
                    )
                    logger.info(f"Juror {juror.name} completed scoring")
                except Exception as e:
                    logger.error(f"Juror {juror.name} failed: {e}")

        if not juror_scores:
            raise OpenJuryEvaluationError("All jurors failed to score the response")

        if len(juror_scores) < len(self.jurors):
            logger.warning(
                f"Only {len(juror_scores)}/{len(self.jurors)} jurors completed successfully"
            )

        return juror_scores

    def _build_trial_result(
        self,
        trial_number: int,
        response: AgentResponse,
        juror_scores: List[JurorScore],
    ) -> TrialResult:
        scored_metrics = ScoreAggregator.compute_all(
            juror_scores=juror_scores,
            criteria=self.config.criteria,
            custom_fn_name=self.config.custom_scoring_function,
        )

        criteria_evaluations: Dict[str, CriterionEvaluation] = {}
        for c in self.config.criteria:
            crit_scores = [js.criterion_scores.get(c.name, 0.0) for js in juror_scores]
            explanations = {
                js.juror_name: js.criterion_explanations.get(c.name, "")
                for js in juror_scores
            }

            total_jw = sum(js.juror_weight for js in juror_scores)
            weighted_mean = (
                sum(
                    js.criterion_scores.get(c.name, 0.0) * js.juror_weight
                    for js in juror_scores
                )
                / total_jw
                if total_jw
                else 0.0
            )

            mean_c = sum(crit_scores) / len(crit_scores) if crit_scores else 0.0
            cov = 0.0
            if len(crit_scores) > 1 and mean_c > 0:
                import statistics

                cov = statistics.stdev(crit_scores) / mean_c
            agreement = max(0.0, min(1.0, 1.0 - cov))

            criteria_evaluations[c.name] = CriterionEvaluation(
                weighted_mean_score=weighted_mean,
                min_juror_score=min(crit_scores) if crit_scores else 0.0,
                max_juror_score=max(crit_scores) if crit_scores else 0.0,
                juror_agreement=agreement,
                weight=c.weight,
                explanations=explanations,
            )

        return TrialResult(
            trial_number=trial_number,
            response_text=response.content,
            scored_metrics=scored_metrics,
            criteria_evaluations=criteria_evaluations,
            juror_scores=juror_scores,
        )

    def score_response(
        self,
        prompt: str,
        endpoint: AgentEndpoint,
        references: Optional[str] = None,
        case_rules: Optional[str] = None,
    ) -> AgentEvalResult:
        """Evaluate one prompt against one endpoint. If num_trials > 1, additional
        trials are run as a consistency audit; quality score comes from trial 1."""

        logger.info(
            f"Starting evaluation: prompt='{prompt[:60]}...' "
            f"endpoint={endpoint.alias or endpoint.url}"
        )

        # Trial 1 — primary quality evaluation
        responses = fetch_all_responses([endpoint], prompt)
        if not responses:
            raise OpenJuryEvaluationError(
                f"No response fetched from endpoint {endpoint.alias or endpoint.url}"
            )
        trial1_response = responses[0]

        juror_scores_t1 = self._run_jurors(
            prompt, trial1_response, references, case_rules
        )
        trial1 = self._build_trial_result(1, trial1_response, juror_scores_t1)

        composite_score = trial1.scored_metrics.weighted_mean
        normalized = (
            composite_score / self.config.score_scale
            if self.config.score_scale
            else 0.0
        )

        trial_results = [trial1]

        # Consistency audit (trials 2..N)
        consistency_result = None
        if self.config.num_trials > 1:
            composite_scores = [composite_score]
            for trial_n in range(2, self.config.num_trials + 1):
                trial_responses = fetch_all_responses([endpoint], prompt)
                if not trial_responses:
                    logger.warning(f"Trial {trial_n} got no response; skipping")
                    continue
                trial_resp = trial_responses[0]
                juror_scores_tn = self._run_jurors(
                    prompt, trial_resp, references, case_rules
                )
                trial_n_result = self._build_trial_result(
                    trial_n, trial_resp, juror_scores_tn
                )
                trial_results.append(trial_n_result)
                composite_scores.append(trial_n_result.scored_metrics.weighted_mean)

            if len(composite_scores) >= 2:
                consistency_result = ScoreAggregator.compute_consistency(
                    composite_scores
                )

        return AgentEvalResult(
            jury_name=self.config.name,
            prompt=prompt,
            endpoint_alias=endpoint.alias,
            model_name=endpoint.model_name,
            score_scale=self.config.score_scale,
            composite_score=composite_score,
            normalized_composite_score=normalized,
            scored_metrics=trial1.scored_metrics,
            criteria_evaluations=trial1.criteria_evaluations,
            juror_scores=juror_scores_t1,
            has_custom_score=self.config.custom_scoring_function is not None,
            consistency_result=consistency_result,
            trial_results=trial_results,
        )

    def score_batch(
        self,
        prompts: List[str],
        endpoint: AgentEndpoint,
        references: Optional[str] = None,
        case_rules: Optional[str] = None,
    ) -> List[AgentEvalResult]:
        """Evaluate multiple prompts against one endpoint sequentially."""
        results: List[AgentEvalResult] = []
        for i, prompt in enumerate(prompts, 1):
            logger.info(f"Batch prompt {i}/{len(prompts)}: {prompt[:60]}...")
            try:
                result = self.score_response(
                    prompt=prompt,
                    endpoint=endpoint,
                    references=references,
                    case_rules=case_rules,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to score prompt {i}: {e}")
                raise OpenJuryEvaluationError(
                    f"Failed to score prompt {i}/{len(prompts)}: {e}"
                ) from e
        return results

    def get_summary(self) -> dict:  # type: ignore[type-arg]
        return {
            "name": self.config.name,
            "description": self.config.description,
            "num_jurors": len(self.jurors),
            "num_criteria": len(self.config.criteria),
            "score_scale": self.config.score_scale,
            "num_trials": self.config.num_trials,
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
                    "has_rubric": criterion.rubric is not None,
                }
                for criterion in self.config.criteria
            ],
        }

    @staticmethod
    def format_result(result: AgentEvalResult) -> str:
        return ResultFormatter.format_result(result)
