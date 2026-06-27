import pytest

from openjury.config import CriterionConfig
from openjury.scoring import (
    ConsistencyResult,
    JurorScore,
    ScoreAggregator,
    ScoredMetrics,
)


def _make_criteria():
    return [
        CriterionConfig(name="clarity", description="Clarity", weight=1.0),
        CriterionConfig(name="accuracy", description="Accuracy", weight=2.0),
    ]


def _make_juror_scores(clarity_scores, accuracy_scores, weights=None):
    weights = weights or [1.0] * len(clarity_scores)
    return [
        JurorScore(
            juror_name=f"Juror{i}",
            juror_weight=weights[i],
            criterion_scores={"clarity": c, "accuracy": a},
            criterion_explanations={"clarity": "ok", "accuracy": "ok"},
        )
        for i, (c, a) in enumerate(zip(clarity_scores, accuracy_scores))
    ]


class TestScoredMetrics:
    def test_weighted_mean_single_juror(self):
        criteria = _make_criteria()
        scores = _make_juror_scores([4.0], [3.0])
        metrics = ScoreAggregator.compute_all(scores, criteria)
        # clarity weight=1, accuracy weight=2; total_weight=3
        # weighted_mean = (4.0*1 + 3.0*2) / 3 = 10/3 ≈ 3.333
        assert abs(metrics.weighted_mean - 10 / 3) < 0.001

    def test_weighted_mean_two_jurors_equal_weight(self):
        criteria = _make_criteria()
        scores = _make_juror_scores([4.0, 2.0], [5.0, 3.0])
        metrics = ScoreAggregator.compute_all(scores, criteria)
        # clarity: mean=3, accuracy: mean=4; weighted=(3*1 + 4*2)/3 = 11/3
        assert abs(metrics.weighted_mean - 11 / 3) < 0.001

    def test_juror_agreement_unanimous(self):
        criteria = _make_criteria()
        # Both jurors give identical scores → std=0 → agreement=1
        scores = _make_juror_scores([4.0, 4.0], [3.0, 3.0])
        metrics = ScoreAggregator.compute_all(scores, criteria)
        assert metrics.juror_agreement == 1.0

    def test_juror_agreement_disagreement(self):
        criteria = _make_criteria()
        # High variance jurors → low agreement
        scores = _make_juror_scores([1.0, 5.0], [1.0, 5.0])
        metrics = ScoreAggregator.compute_all(scores, criteria)
        assert metrics.juror_agreement < 0.5

    def test_min_max_scores(self):
        criteria = _make_criteria()
        scores = _make_juror_scores([5.0, 2.0], [5.0, 2.0])
        metrics = ScoreAggregator.compute_all(scores, criteria)
        assert metrics.min_score < metrics.max_score

    def test_harmonic_mean_penalises_low_scores(self):
        criteria = _make_criteria()
        # One juror scores very low on clarity
        scores = _make_juror_scores([1.0, 5.0], [5.0, 5.0])
        metrics = ScoreAggregator.compute_all(scores, criteria)
        # Harmonic mean should be lower than arithmetic mean
        assert metrics.harmonic_mean <= metrics.mean

    def test_weakest_link(self):
        criteria = _make_criteria()
        scores = _make_juror_scores([1.0, 1.0], [5.0, 5.0])
        metrics = ScoreAggregator.compute_all(scores, criteria)
        # weakest_link = min crit weighted-avg on score scale
        # clarity weighted_avg = 1.0, accuracy weighted_avg = 5.0 → weakest = 1.0
        assert abs(metrics.weakest_link - 1.0) < 0.001

    def test_custom_function_applied(self):
        criteria = _make_criteria()
        scores = _make_juror_scores([4.0], [4.0])

        def always_five(juror_scores, crit):
            return 5.0

        metrics = ScoreAggregator.compute_all(scores, criteria, custom_fn=always_five)
        assert metrics.custom == 5.0

    def test_no_custom_function_gives_none(self):
        criteria = _make_criteria()
        scores = _make_juror_scores([4.0], [4.0])
        metrics = ScoreAggregator.compute_all(scores, criteria)
        assert metrics.custom is None

    def test_empty_juror_scores_raises(self):
        criteria = _make_criteria()
        with pytest.raises(ValueError, match="No juror scores"):
            ScoreAggregator.compute_all([], criteria)

    def test_empty_criteria_raises(self):
        scores = _make_juror_scores([4.0], [4.0])
        with pytest.raises(ValueError, match="No criteria"):
            ScoreAggregator.compute_all(scores, [])

    def test_returns_scored_metrics_model(self):
        criteria = _make_criteria()
        scores = _make_juror_scores([3.0], [4.0])
        metrics = ScoreAggregator.compute_all(scores, criteria)
        assert isinstance(metrics, ScoredMetrics)


class TestConsistencyResult:
    def test_compute_consistency_low_variance(self):
        result = ScoreAggregator.compute_consistency([3.9, 4.0, 4.1])
        assert isinstance(result, ConsistencyResult)
        assert result.num_trials == 3
        assert result.score_std < 0.1
        assert "low variance" in result.interpretation

    def test_compute_consistency_high_variance(self):
        result = ScoreAggregator.compute_consistency([1.0, 3.0, 5.0])
        assert result.score_std > 0.3
        assert "high variance" in result.interpretation

    def test_compute_consistency_needs_two_trials(self):
        with pytest.raises(ValueError, match="at least 2"):
            ScoreAggregator.compute_consistency([4.0])

    def test_compute_consistency_score_mean_informational(self):
        trials = [3.0, 5.0]
        result = ScoreAggregator.compute_consistency(trials)
        assert result.score_mean == 4.0
        assert result.score_min == 3.0
        assert result.score_max == 5.0

    def test_register_unregister_list(self):
        import warnings

        def dummy(js, cr):
            return 1.0

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            ScoreAggregator.register("dummy_fn", dummy)
        assert "dummy_fn" in ScoreAggregator.list_custom()
        ScoreAggregator.unregister("dummy_fn")
        assert "dummy_fn" not in ScoreAggregator.list_custom()
