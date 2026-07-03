import dataclasses
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from openjury.assertion_resolution import resolve_item_assertions
from openjury.assertions import evaluate_assertions, score_assertions
from openjury.batch_summary import BatchEvalResult, aggregate_batch_results
from openjury.config import AgentResponse, AssertionConfig, JuryConfig
from openjury.endpoint_fetcher import AgentEndpoint, fetch_agent_response
from openjury.errors import (
    EvaluationErrorCode,
    JurorErrorCode,
    OpenJuryEvaluationError,
    OpenJuryInitializationError,
)
from openjury.execution import (
    EvalItemStatus,
    EvaluationItem,
    ExecutionOptions,
    ItemEvalResult,
    JurorFailure,
    ProgressEvent,
    ProgressEventType,
    ScoringResult,
    classify_item_error,
)
from openjury.juror import Juror
from openjury.logger import logger
from openjury.output_format import (
    AgentEvalResult,
    CriterionEvaluation,
    ResultFormatter,
    TrialResult,
)
from openjury.scoring import (
    JurorScore,
    ScoreAggregator,
    ScoringFunction,
    _criterion_agreement,
)

__all__ = ["OpenJury", "OpenJuryEvaluationError", "OpenJuryInitializationError"]


class OpenJury:
    def __init__(
        self,
        config: JuryConfig,
        custom_scoring_functions: Optional[Dict[str, ScoringFunction]] = None,
        parallel_execution: bool = True,
    ):
        if not parallel_execution:
            warnings.warn(
                "OpenJury(parallel_execution=False) is deprecated. "
                "Use ExecutionOptions(max_juror_workers=1) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.config = config
        self.parallel_execution = parallel_execution
        self.jurors: List[Juror] = []

        self._custom_fn: Optional[ScoringFunction] = None
        if config.custom_scoring_function:
            fn_name = config.custom_scoring_function
            fn_map = custom_scoring_functions or {}
            if fn_name in fn_map:
                self._custom_fn = fn_map[fn_name]
            elif fn_name in ScoreAggregator._custom_functions:
                self._custom_fn = ScoreAggregator._custom_functions[fn_name]
            else:
                raise OpenJuryInitializationError(
                    f"Custom scoring function '{fn_name}' is not registered. "
                    f"Pass custom_scoring_functions={{'{fn_name}': fn}} to OpenJury()."
                )

        for cfg in config.jurors:
            try:
                juror = Juror(
                    cfg,
                    jury_llm_provider=config.llm_provider,
                )
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

    @staticmethod
    def _resolve_options(options: ExecutionOptions | None) -> ExecutionOptions:
        return options if options is not None else ExecutionOptions()

    def _resolve_contested_threshold(self, options: ExecutionOptions) -> float:
        if options.contested_threshold is not None:
            return options.contested_threshold
        return self.config.contested_threshold

    @staticmethod
    def _lowest_criterion(
        criteria_evaluations: Dict[str, CriterionEvaluation],
    ) -> Tuple[Optional[str], Optional[float]]:
        if not criteria_evaluations:
            return None, None
        lowest_name = min(
            criteria_evaluations,
            key=lambda name: criteria_evaluations[name].weighted_mean_score,
        )
        return lowest_name, criteria_evaluations[lowest_name].weighted_mean_score

    def _emit_progress(self, options: ExecutionOptions, event: ProgressEvent) -> None:
        if options.on_progress is None:
            return
        if event.timestamp_ms is None:
            event.timestamp_ms = time.perf_counter() * 1000.0
        options.on_progress(event)

    def _resolve_juror_workers(self, options: ExecutionOptions, count: int) -> int:
        if not self.parallel_execution or count <= 1:
            return 1
        return min(count, options.max_juror_workers)

    def _score_with_juror(
        self,
        juror: Juror,
        prompt: str,
        response: AgentResponse,
        references: Optional[str],
        case_rules: Optional[str],
        options: ExecutionOptions,
    ) -> JurorScore:
        with (options or ExecutionOptions()).outbound_slot():
            return juror.evaluate(
                prompt=prompt,
                response=response,
                criteria=self.config.criteria,
                score_min=self.config.score_min,
                score_scale=self.config.score_scale,
                max_retries=self.config.max_retries,
                evaluation_template=self.config.evaluation_template,
                references=references,
                case_rules=case_rules,
            )

    def _juror_failure_from_exception(
        self, juror: Juror, exc: Exception
    ) -> JurorFailure:
        code = getattr(exc, "code", JurorErrorCode.JUROR_ERROR)
        return JurorFailure(juror_name=juror.name, code=str(code), message=str(exc))

    def run_jurors(
        self,
        prompt: str,
        response: AgentResponse,
        *,
        references: Optional[str] = None,
        case_rules: Optional[str] = None,
        jurors_to_run: Sequence[str] | None = None,
        options: ExecutionOptions | None = None,
    ) -> ScoringResult:
        """Run jurors against a response; collect partial successes and failures."""
        opts = self._resolve_options(options)
        active_jurors = self.jurors
        if jurors_to_run is not None:
            names = set(jurors_to_run)
            active_jurors = [j for j in self.jurors if j.name in names]
            if not active_jurors:
                raise OpenJuryEvaluationError(
                    f"No matching jurors for names: {sorted(names)}"
                )

        juror_scores: List[JurorScore] = []
        juror_failures: List[JurorFailure] = []

        def run_one(juror: Juror) -> None:
            opts.check_cancelled()
            if opts.on_progress is not None:
                self._emit_progress(
                    opts,
                    ProgressEvent(
                        type=ProgressEventType.JUROR_STARTED,
                        juror_name=juror.name,
                    ),
                )
            try:
                score = self._score_with_juror(
                    juror, prompt, response, references, case_rules, opts
                )
                juror_scores.append(score)
                logger.info(f"Juror {juror.name} completed scoring")
                if opts.on_progress is not None:
                    self._emit_progress(
                        opts,
                        ProgressEvent(
                            type=ProgressEventType.JUROR_COMPLETED,
                            juror_name=juror.name,
                        ),
                    )
            except Exception as exc:
                logger.error(f"Juror {juror.name} failed: {exc}")
                juror_failures.append(self._juror_failure_from_exception(juror, exc))

        max_workers = self._resolve_juror_workers(opts, len(active_jurors))
        if max_workers > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(run_one, juror) for juror in active_jurors]
                for future in futures:
                    future.result()
        else:
            for juror in active_jurors:
                run_one(juror)

        if juror_scores and juror_failures:
            logger.warning(
                f"Only {len(juror_scores)}/{len(active_jurors)} jurors completed successfully"
            )

        return ScoringResult(
            juror_scores=juror_scores,
            juror_failures=juror_failures,
            all_jurors_succeeded=len(juror_failures) == 0,
        )

    def _build_trial_result(
        self,
        trial_number: int,
        response: AgentResponse,
        juror_scores: List[JurorScore],
        assertions: Sequence[AssertionConfig],
    ) -> TrialResult:
        scored_metrics = ScoreAggregator.compute_all(
            juror_scores=juror_scores,
            criteria=self.config.criteria,
            custom_fn=self._custom_fn,
        )

        total_jw = sum(js.juror_weight for js in juror_scores)
        criteria_evaluations: Dict[str, CriterionEvaluation] = {}
        for c in self.config.criteria:
            crit_scores = [js.criterion_scores.get(c.name, 0.0) for js in juror_scores]
            explanations = {
                js.juror_name: js.criterion_explanations.get(c.name, "")
                for js in juror_scores
            }
            weighted_mean = (
                sum(
                    js.criterion_scores.get(c.name, 0.0) * js.juror_weight
                    for js in juror_scores
                )
                / total_jw
                if total_jw
                else 0.0
            )
            criteria_evaluations[c.name] = CriterionEvaluation(
                weighted_mean_score=weighted_mean,
                min_juror_score=min(crit_scores) if crit_scores else 0.0,
                max_juror_score=max(crit_scores) if crit_scores else 0.0,
                juror_agreement=_criterion_agreement(crit_scores),
                weight=c.weight,
                explanations=explanations,
            )

        assertion_results = evaluate_assertions(response.content, list(assertions))
        assertion_score, assertions_passed = score_assertions(assertion_results)

        return TrialResult(
            trial_number=trial_number,
            response_text=response.content,
            scored_metrics=scored_metrics,
            criteria_evaluations=criteria_evaluations,
            juror_scores=juror_scores,
            assertion_results=assertion_results,
            assertion_score=assertion_score,
            assertions_passed=assertions_passed,
        )

    def _resolve_assertion_policy(
        self,
        assertions: Optional[Sequence[AssertionConfig]],
        assertion_threshold: Optional[float],
        quality_threshold: Optional[float],
    ) -> tuple[Sequence[AssertionConfig], Optional[float], Optional[float]]:
        inline_assertions = [] if assertions is None else list(assertions)
        (
            resolved_assertions,
            resolved_assertion_threshold,
            resolved_quality_threshold,
        ) = resolve_item_assertions(
            self.config,
            profile_ids=[],
            inline_assertions=inline_assertions,
            item_assertion_threshold=assertion_threshold,
            item_quality_threshold=quality_threshold,
        )
        if (
            resolved_assertion_threshold is not None
            and not 0.0 <= resolved_assertion_threshold <= 1.0
        ):
            raise ValueError("assertion_threshold must be between 0 and 1")
        if resolved_quality_threshold is not None and not (
            0.0 <= resolved_quality_threshold <= self.config.score_scale
        ):
            raise ValueError(
                "quality_threshold must be between 0 and score_scale "
                f"({self.config.score_scale})"
            )
        return (
            resolved_assertions,
            resolved_assertion_threshold,
            resolved_quality_threshold,
        )

    def _assemble_eval_result(
        self,
        *,
        prompt: str,
        trial: TrialResult,
        juror_scores: List[JurorScore],
        juror_failures: List[JurorFailure],
        endpoint_alias: Optional[str] = None,
        model_name: Optional[str] = None,
        fetch_metadata=None,
        consistency_result=None,
        trial_results: Optional[List[TrialResult]] = None,
        assertion_threshold: Optional[float] = None,
        quality_threshold: Optional[float] = None,
        item_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        contested_threshold: Optional[float] = None,
        evaluation_duration_ms: Optional[int] = None,
    ) -> AgentEvalResult:
        composite_score = trial.scored_metrics.weighted_mean
        normalized = (
            composite_score / self.config.score_scale
            if self.config.score_scale
            else 0.0
        )
        meets_assertion_threshold = (
            assertion_threshold is None or trial.assertion_score >= assertion_threshold
        )
        meets_quality_threshold = (
            quality_threshold is None or composite_score >= quality_threshold
        )
        resolved_contested_threshold = (
            contested_threshold
            if contested_threshold is not None
            else self.config.contested_threshold
        )
        lowest_name, lowest_score = self._lowest_criterion(trial.criteria_evaluations)
        return AgentEvalResult(
            jury_name=self.config.name,
            prompt=prompt,
            endpoint_alias=endpoint_alias,
            model_name=model_name,
            score_min=self.config.score_min,
            score_scale=self.config.score_scale,
            composite_score=composite_score,
            normalized_composite_score=normalized,
            scored_metrics=trial.scored_metrics,
            criteria_evaluations=trial.criteria_evaluations,
            juror_scores=juror_scores,
            assertion_results=trial.assertion_results,
            assertion_score=trial.assertion_score,
            assertions_passed=trial.assertions_passed,
            passed=(
                trial.assertions_passed
                and meets_assertion_threshold
                and meets_quality_threshold
            ),
            quality_passed=meets_quality_threshold,
            assertion_threshold_met=meets_assertion_threshold,
            quality_threshold=quality_threshold,
            assertion_threshold=assertion_threshold,
            item_id=item_id,
            metadata=metadata or {},
            lowest_criterion=lowest_name,
            lowest_criterion_score=lowest_score,
            contested=trial.scored_metrics.juror_agreement
            < resolved_contested_threshold,
            evaluation_duration_ms=evaluation_duration_ms,
            consistency_result=consistency_result,
            trial_results=trial_results or [trial],
            fetch_metadata=fetch_metadata,
            juror_failures=juror_failures,
        )

    def score_existing_response(
        self,
        prompt: str,
        agent_response: AgentResponse,
        *,
        references: Optional[str] = None,
        case_rules: Optional[str] = None,
        assertions: Optional[Sequence[AssertionConfig]] = None,
        assertion_threshold: Optional[float] = None,
        quality_threshold: Optional[float] = None,
        jurors_to_run: Sequence[str] | None = None,
        options: ExecutionOptions | None = None,
    ) -> "AgentEvalResult":
        """Score a pre-fetched agent response without calling the endpoint again.

        Per-call assertions supplement global_assertions. Pass an empty sequence
        for global checks only.

        Raises OpenJuryEvaluationError if all jurors fail. Partial juror failures
        are surfaced in the returned AgentEvalResult.juror_failures list.
        Use run_jurors() directly for lower-level access to the ScoringResult.
        """
        scoring = self.run_jurors(
            prompt,
            agent_response,
            references=references,
            case_rules=case_rules,
            jurors_to_run=jurors_to_run,
            options=options,
        )

        if not scoring.juror_scores:
            raise OpenJuryEvaluationError(
                "All jurors failed to score the response",
                code=EvaluationErrorCode.ALL_JURORS_FAILED,
            )

        assertion_policy = self._resolve_assertion_policy(
            assertions, assertion_threshold, quality_threshold
        )
        trial = self._build_trial_result(
            1, agent_response, scoring.juror_scores, assertion_policy[0]
        )
        return self._assemble_eval_result(
            prompt=prompt,
            trial=trial,
            juror_scores=scoring.juror_scores,
            juror_failures=scoring.juror_failures,
            assertion_threshold=assertion_policy[1],
            quality_threshold=assertion_policy[2],
            contested_threshold=self._resolve_contested_threshold(
                self._resolve_options(options)
            ),
        )

    def evaluate(
        self,
        prompt: str,
        endpoint: AgentEndpoint,
        *,
        references: Optional[str] = None,
        case_rules: Optional[str] = None,
        assertions: Optional[Sequence[AssertionConfig]] = None,
        assertion_threshold: Optional[float] = None,
        quality_threshold: Optional[float] = None,
        item_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        evaluation_duration_ms: Optional[int] = None,
        options: ExecutionOptions | None = None,
    ) -> AgentEvalResult:
        """Fetch from endpoint and score the response.

        Per-call assertions supplement global_assertions. Pass an empty sequence
        for global checks only.
        """
        opts = self._resolve_options(options)
        contested_threshold = self._resolve_contested_threshold(opts)
        assertion_policy = self._resolve_assertion_policy(
            assertions, assertion_threshold, quality_threshold
        )

        logger.info(
            f"Starting evaluation: prompt='{prompt[:60]}...' "
            f"endpoint={endpoint.alias or endpoint.url}"
        )

        fetch_result = fetch_agent_response(endpoint, prompt, options=opts)
        trial1_response = fetch_result.response

        scoring1 = self.run_jurors(
            prompt,
            trial1_response,
            references=references,
            case_rules=case_rules,
            options=opts,
        )
        if not scoring1.juror_scores:
            raise OpenJuryEvaluationError(
                "All jurors failed to score trial 1 response",
                code=EvaluationErrorCode.ALL_JURORS_FAILED,
            )
        trial1 = self._build_trial_result(
            1, trial1_response, scoring1.juror_scores, assertion_policy[0]
        )
        trial_results = [trial1]

        consistency_result = None
        if self.config.num_trials > 1:
            composite_scores = [trial1.scored_metrics.weighted_mean]
            for trial_n in range(2, self.config.num_trials + 1):
                opts.check_cancelled()
                try:
                    trial_fetch = fetch_agent_response(endpoint, prompt, options=opts)
                except Exception as exc:
                    logger.warning(f"Trial {trial_n} fetch failed: {exc}")
                    continue

                trial_scoring = self.run_jurors(
                    prompt,
                    trial_fetch.response,
                    references=references,
                    case_rules=case_rules,
                    options=opts,
                )
                if not trial_scoring.juror_scores:
                    logger.warning(f"Trial {trial_n} got no juror scores; skipping")
                    continue

                trial_n_result = self._build_trial_result(
                    trial_n,
                    trial_fetch.response,
                    trial_scoring.juror_scores,
                    assertion_policy[0],
                )
                trial_results.append(trial_n_result)
                composite_scores.append(trial_n_result.scored_metrics.weighted_mean)

            if len(composite_scores) >= 2:
                consistency_result = ScoreAggregator.compute_consistency(
                    composite_scores
                )

        result = self._assemble_eval_result(
            prompt=prompt,
            trial=trial1,
            juror_scores=scoring1.juror_scores,
            juror_failures=scoring1.juror_failures,
            endpoint_alias=endpoint.alias,
            model_name=endpoint.model_name,
            fetch_metadata=fetch_result.metadata,
            consistency_result=consistency_result,
            trial_results=trial_results,
            assertion_threshold=assertion_policy[1],
            quality_threshold=assertion_policy[2],
            item_id=item_id,
            metadata=metadata,
            contested_threshold=contested_threshold,
            evaluation_duration_ms=evaluation_duration_ms,
        )
        return result

    def score_response(
        self,
        prompt: str,
        endpoint: AgentEndpoint,
        *,
        references: Optional[str] = None,
        case_rules: Optional[str] = None,
        assertions: Optional[Sequence[AssertionConfig]] = None,
        assertion_threshold: Optional[float] = None,
        quality_threshold: Optional[float] = None,
        options: ExecutionOptions | None = None,
    ) -> AgentEvalResult:
        """Backward-compatible alias for :meth:`evaluate`."""
        return self.evaluate(
            prompt,
            endpoint,
            references=references,
            case_rules=case_rules,
            assertions=assertions,
            assertion_threshold=assertion_threshold,
            quality_threshold=quality_threshold,
            options=options,
        )

    def _evaluate_one_item(
        self,
        item: EvaluationItem,
        index: int,
        endpoint: AgentEndpoint | None,
        *,
        references: Optional[str],
        case_rules: Optional[str],
        options: ExecutionOptions,
    ) -> ItemEvalResult:
        options.check_cancelled()
        item_endpoint = item.endpoint if item.endpoint is not None else endpoint
        if item_endpoint is None:
            status, code, stage = classify_item_error(
                ValueError("No endpoint configured for evaluation item")
            )
            return ItemEvalResult(
                item=item,
                index=index,
                error=ValueError("No endpoint configured for evaluation item"),
                status=status,
                error_code=code,
                error_message="No endpoint configured for evaluation item",
                error_stage=stage,
            )

        item_refs = item.references if item.references is not None else references
        item_rules = item.case_rules if item.case_rules is not None else case_rules

        item_opts = dataclasses.replace(
            options,
            ground_truth=(
                item.ground_truth
                if item.ground_truth is not None
                else options.ground_truth
            ),
            idempotency_key=(
                item.item_id if item.item_id is not None else options.idempotency_key
            ),
        )
        item_opts._outbound_semaphore = options._outbound_semaphore

        self._emit_progress(
            options,
            ProgressEvent(
                type=ProgressEventType.ITEM_STARTED,
                item_index=index,
                item_id=item.item_id,
            ),
        )
        started = time.perf_counter()
        try:
            result = self.evaluate(
                prompt=item.prompt,
                endpoint=item_endpoint,
                references=item_refs,
                case_rules=item_rules,
                assertions=item.assertions,
                assertion_threshold=item.assertion_threshold,
                quality_threshold=item.quality_threshold,
                item_id=item.item_id,
                metadata=item.metadata,
                evaluation_duration_ms=None,
                options=item_opts,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            result = result.model_copy(update={"evaluation_duration_ms": duration_ms})
            self._emit_progress(
                options,
                ProgressEvent(
                    type=ProgressEventType.ITEM_COMPLETED,
                    item_index=index,
                    item_id=item.item_id,
                ),
            )
            return ItemEvalResult(
                item=item,
                index=index,
                result=result,
                status=EvalItemStatus.SCORED,
                evaluation_duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.error(f"Failed to evaluate item {index}: {exc}")
            status, code, stage = classify_item_error(exc)
            return ItemEvalResult(
                item=item,
                index=index,
                error=exc,
                status=status,
                error_code=code,
                error_message=str(exc),
                error_stage=stage,
                evaluation_duration_ms=duration_ms,
            )

    def evaluate_items(
        self,
        items: Sequence[EvaluationItem],
        endpoint: AgentEndpoint | None = None,
        *,
        references: Optional[str] = None,
        case_rules: Optional[str] = None,
        options: ExecutionOptions | None = None,
        on_item_complete: Callable[[ItemEvalResult], None] | None = None,
    ) -> List[ItemEvalResult]:
        """Evaluate multiple dataset items with bounded concurrency."""
        opts = self._resolve_options(options)
        if not items:
            return []
        if endpoint is None and any(item.endpoint is None for item in items):
            raise ValueError(
                "endpoint is required when any EvaluationItem lacks item.endpoint"
            )

        results: List[Optional[ItemEvalResult]] = [None] * len(items)
        max_workers = min(len(items), max(1, opts.max_item_workers))

        def run_index(index: int, item: EvaluationItem) -> None:
            item_result = self._evaluate_one_item(
                item,
                index,
                endpoint,
                references=references,
                case_rules=case_rules,
                options=opts,
            )
            results[index] = item_result
            if on_item_complete is not None:
                on_item_complete(item_result)

        if max_workers > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(run_index, i, item) for i, item in enumerate(items)
                ]
                for future in futures:
                    future.result()
        else:
            for index, item in enumerate(items):
                run_index(index, item)

        return [r for r in results if r is not None]

    def evaluate_items_with_summary(
        self,
        items: Sequence[EvaluationItem],
        endpoint: AgentEndpoint | None = None,
        *,
        references: Optional[str] = None,
        case_rules: Optional[str] = None,
        options: ExecutionOptions | None = None,
        on_item_complete: Callable[[ItemEvalResult], None] | None = None,
    ) -> BatchEvalResult:
        """Evaluate items and return run-level aggregate metrics."""
        started_at = datetime.now(timezone.utc)
        run_started = time.perf_counter()
        opts = self._resolve_options(options)
        item_results = self.evaluate_items(
            items,
            endpoint,
            references=references,
            case_rules=case_rules,
            options=opts,
            on_item_complete=on_item_complete,
        )
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((time.perf_counter() - run_started) * 1000)
        summary = aggregate_batch_results(
            item_results,
            score_scale=self.config.score_scale,
            score_min=self.config.score_min,
            contested_threshold=self._resolve_contested_threshold(opts),
            quality_threshold=self.config.assertion_policy.quality_threshold,
            duration_ms=duration_ms,
        )
        return BatchEvalResult(
            items=item_results,
            summary=summary,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
        )

    def score_batch(
        self,
        prompts: List[str],
        endpoint: AgentEndpoint,
        references: Optional[str] = None,
        case_rules: Optional[str] = None,
        *,
        options: ExecutionOptions | None = None,
    ) -> List[AgentEvalResult]:
        """Evaluate multiple prompts against one endpoint sequentially."""
        items = [EvaluationItem(prompt=prompt) for prompt in prompts]
        batch_options = dataclasses.replace(
            self._resolve_options(options), max_item_workers=1
        )
        item_results = self.evaluate_items(
            items,
            endpoint,
            references=references,
            case_rules=case_rules,
            options=batch_options,
        )
        results: List[AgentEvalResult] = []
        for i, item_result in enumerate(item_results, 1):
            if item_result.error is not None:
                raise OpenJuryEvaluationError(
                    f"Failed to score prompt {i}/{len(prompts)}: {item_result.error}"
                ) from item_result.error
            if item_result.result is None:
                raise OpenJuryEvaluationError(
                    f"Prompt {i}/{len(prompts)}: evaluation completed with no result",
                    code=EvaluationErrorCode.ALL_JURORS_FAILED,
                )
            results.append(item_result.result)
        return results

    def get_summary(self) -> dict:  # type: ignore[type-arg]
        return {
            "name": self.config.name,
            "description": self.config.description,
            "num_jurors": len(self.jurors),
            "num_criteria": len(self.config.criteria),
            "num_global_assertions": len(self.config.global_assertions),
            "num_assertion_profiles": len(self.config.assertion_profiles),
            "assertion_threshold": self.config.assertion_policy.assertion_threshold,
            "quality_threshold": self.config.assertion_policy.quality_threshold,
            "score_min": self.config.score_min,
            "score_scale": self.config.score_scale,
            "num_trials": self.config.num_trials,
            "jurors": [
                {
                    "name": juror.name,
                    "model": juror.llm_config.model_name,
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
            "global_assertions": [
                assertion.model_dump(mode="json")
                for assertion in self.config.global_assertions
            ],
            "assertion_profiles": {
                profile_id: profile.model_dump(mode="json")
                for profile_id, profile in self.config.assertion_profiles.items()
            },
        }

    @staticmethod
    def format_result(result: AgentEvalResult) -> str:
        return ResultFormatter.format_result(result)
