"""
Unit tests for quality score service.

Tests cover:
- content_length scoring (various durations)
- coherence scoring (direct mapping from metric)
- balance scoring (balanced vs unbalanced ratios)
- engagement scoring (good banter, turn counts)
- overall score calculation (weighted average)
- rating assignment (thresholds: poor/fair/good/excellent)
- strength generation (matches positive metrics)
- improvement generation (identifies weak areas)
- full calculate_quality_scores integration
- generate_interpretation integration
"""

import pytest
from src.schemas.quality_metrics import QualityMetricsData
from src.services.quality_score_service import QualityScoreService, _rating_from_score


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def service():
    return QualityScoreService()


@pytest.fixture
def good_metrics():
    """Metrics representing a good-quality episode."""
    return QualityMetricsData(
        total_words=2450,
        duration_estimate_minutes=16.3,
        coherence_score=0.78,
        tone="casual",
        speaker_balance_ratio=1.2,
        is_balanced=True,
        max_monologue_words=185,
        dialogue_turns=47,
        has_good_banter=True,
    )


@pytest.fixture
def poor_metrics():
    """Metrics representing a poor-quality episode."""
    return QualityMetricsData(
        total_words=300,
        duration_estimate_minutes=2.0,
        coherence_score=0.30,
        tone="academic",
        speaker_balance_ratio=5.0,
        is_balanced=False,
        max_monologue_words=300,
        dialogue_turns=2,
        has_good_banter=False,
    )


# ============================================================================
# _rating_from_score TESTS
# ============================================================================

def test_rating_excellent():
    assert _rating_from_score(0.9) == "excellent"
    assert _rating_from_score(1.0) == "excellent"
    assert _rating_from_score(0.8) == "excellent"


def test_rating_good():
    assert _rating_from_score(0.75) == "good"
    assert _rating_from_score(0.6) == "good"


def test_rating_fair():
    assert _rating_from_score(0.5) == "fair"
    assert _rating_from_score(0.4) == "fair"


def test_rating_poor():
    assert _rating_from_score(0.39) == "poor"
    assert _rating_from_score(0.0) == "poor"


# ============================================================================
# CONTENT LENGTH SCORE TESTS
# ============================================================================

def test_content_length_score_very_short(service):
    """Under 5 min should be poor."""
    score, rating = service._calculate_content_length_score(2.0)
    assert score == 0.3
    assert rating == "poor"


def test_content_length_score_short(service):
    """5-10 min should be fair."""
    score, rating = service._calculate_content_length_score(7.0)
    assert score == 0.55
    assert rating == "fair"


def test_content_length_score_medium(service):
    """10-30 min should be excellent (0.85 >= 0.8 threshold)."""
    score, rating = service._calculate_content_length_score(20.0)
    assert score == 0.85
    assert rating == "excellent"


def test_content_length_score_long(service):
    """30+ min should be excellent."""
    score, rating = service._calculate_content_length_score(45.0)
    assert score == 1.0
    assert rating == "excellent"


def test_content_length_score_boundary_5_min(service):
    """Exactly 5 min should be fair (>= 5)."""
    score, rating = service._calculate_content_length_score(5.0)
    assert score == 0.55


def test_content_length_score_boundary_10_min(service):
    """Exactly 10 min should be good (>= 10)."""
    score, rating = service._calculate_content_length_score(10.0)
    assert score == 0.85


def test_content_length_score_boundary_30_min(service):
    """Exactly 30 min should be excellent (>= 30)."""
    score, rating = service._calculate_content_length_score(30.0)
    assert score == 1.0


# ============================================================================
# COHERENCE SCORE TESTS
# ============================================================================

def test_coherence_score_high(service):
    """High coherence should map directly."""
    score, rating = service._calculate_coherence_score(0.9)
    assert score == 0.9
    assert rating == "excellent"


def test_coherence_score_medium(service):
    score, rating = service._calculate_coherence_score(0.7)
    assert score == 0.7
    assert rating == "good"


def test_coherence_score_low(service):
    score, rating = service._calculate_coherence_score(0.3)
    assert score == 0.3
    assert rating == "poor"


def test_coherence_score_zero(service):
    score, rating = service._calculate_coherence_score(0.0)
    assert score == 0.0
    assert rating == "poor"


# ============================================================================
# BALANCE SCORE TESTS
# ============================================================================

def test_balance_score_balanced(service):
    """Balanced flag True should give excellent."""
    score, rating = service._calculate_balance_score(True, 1.2)
    assert score == 1.0
    assert rating == "excellent"


def test_balance_score_near_balanced_low(service):
    """Ratio 0.25-0.4 but is_balanced=False => good."""
    score, rating = service._calculate_balance_score(False, 0.35)
    assert score == 0.7
    assert rating == "good"


def test_balance_score_near_balanced_high(service):
    """Ratio 2.5-4.0 but is_balanced=False => good."""
    score, rating = service._calculate_balance_score(False, 3.5)
    assert score == 0.7
    assert rating == "good"


def test_balance_score_imbalanced(service):
    """Extreme imbalance should be fair."""
    score, rating = service._calculate_balance_score(False, 10.0)
    assert score == 0.5
    assert rating == "fair"


# ============================================================================
# ENGAGEMENT SCORE TESTS
# ============================================================================

def test_engagement_score_excellent(service):
    """Good banter + >50 turns => excellent."""
    score, rating = service._calculate_engagement_score(True, 55, 100)
    assert score == 1.0
    assert rating == "excellent"


def test_engagement_score_good_banter(service):
    """Good banter but <=50 turns => score 0.8 => excellent."""
    score, rating = service._calculate_engagement_score(True, 30, 150)
    assert score == 0.8
    assert rating == "excellent"


def test_engagement_score_many_turns_no_banter(service):
    """No good banter but >30 turns => fair."""
    score, rating = service._calculate_engagement_score(False, 35, 250)
    assert score == 0.6
    assert rating == "good"  # 0.6 falls in "good" range


def test_engagement_score_poor(service):
    """No good banter and <=30 turns => poor."""
    score, rating = service._calculate_engagement_score(False, 5, 300)
    assert score == 0.4
    assert rating == "fair"  # 0.4 is at the boundary; fair


# ============================================================================
# OVERALL SCORE TESTS
# ============================================================================

def test_overall_score_weighted_average(service):
    """Verify weighted average formula."""
    score, rating = service._calculate_overall_score(0.8, 0.8, 0.8, 0.8)
    assert abs(score - 0.8) < 0.001
    assert rating == "excellent"


def test_overall_score_mixed(service):
    """Poor balance drags down overall."""
    # content=1.0 (20%), coherence=0.9 (25%), balance=0.5 (30%), engagement=0.8 (25%)
    # = 0.2 + 0.225 + 0.15 + 0.2 = 0.775
    score, rating = service._calculate_overall_score(1.0, 0.9, 0.5, 0.8)
    assert abs(score - 0.775) < 0.001
    assert rating == "good"


# ============================================================================
# CALCULATE_QUALITY_SCORES INTEGRATION TESTS
# ============================================================================

def test_calculate_quality_scores_returns_five_dimensions(service, good_metrics):
    scores = service.calculate_quality_scores(good_metrics)
    dimensions = {qs.dimension for qs in scores}
    assert dimensions == {"content_length", "coherence", "balance", "engagement", "overall"}


def test_calculate_quality_scores_all_in_range(service, good_metrics):
    scores = service.calculate_quality_scores(good_metrics)
    for qs in scores:
        assert 0.0 <= qs.score <= 1.0
        assert qs.rating in {"poor", "fair", "good", "excellent"}


def test_calculate_quality_scores_good_metrics(service, good_metrics):
    scores = service.calculate_quality_scores(good_metrics)
    overall = next(qs for qs in scores if qs.dimension == "overall")
    assert overall.rating in {"good", "excellent"}


def test_calculate_quality_scores_poor_metrics(service, poor_metrics):
    scores = service.calculate_quality_scores(poor_metrics)
    overall = next(qs for qs in scores if qs.dimension == "overall")
    assert overall.rating in {"poor", "fair"}


# ============================================================================
# GENERATE_STRENGTHS TESTS
# ============================================================================

def test_generate_strengths_balanced_episode(service, good_metrics):
    strengths = service.generate_strengths(good_metrics)
    assert any("balance" in s.lower() for s in strengths)


def test_generate_strengths_good_banter(service, good_metrics):
    strengths = service.generate_strengths(good_metrics)
    assert any("dialogue" in s.lower() or "banter" in s.lower() or "turns" in s.lower() for s in strengths)


def test_generate_strengths_high_coherence(service, good_metrics):
    strengths = service.generate_strengths(good_metrics)
    assert any("coherence" in s.lower() or "conversational" in s.lower() for s in strengths)


def test_generate_strengths_short_episode_no_length_strength(service):
    metrics = QualityMetricsData(
        total_words=200,
        duration_estimate_minutes=1.3,
        coherence_score=0.5,
        tone="casual",
        speaker_balance_ratio=1.0,
        is_balanced=True,
        max_monologue_words=50,
        dialogue_turns=5,
        has_good_banter=True,
    )
    strengths = service.generate_strengths(metrics)
    assert not any("length" in s.lower() for s in strengths)


# ============================================================================
# GENERATE_IMPROVEMENTS TESTS
# ============================================================================

def test_generate_improvements_imbalanced(service, poor_metrics):
    improvements = service.generate_improvements(poor_metrics)
    assert any("balance" in imp.lower() for imp in improvements)


def test_generate_improvements_long_monologue(service, poor_metrics):
    improvements = service.generate_improvements(poor_metrics)
    assert any("monologue" in imp.lower() for imp in improvements)


def test_generate_improvements_few_turns(service, poor_metrics):
    improvements = service.generate_improvements(poor_metrics)
    assert any("turn" in imp.lower() for imp in improvements)


def test_generate_improvements_low_coherence(service, poor_metrics):
    improvements = service.generate_improvements(poor_metrics)
    assert any("coherence" in imp.lower() or "sentence" in imp.lower() for imp in improvements)


def test_generate_improvements_short_duration(service, poor_metrics):
    improvements = service.generate_improvements(poor_metrics)
    assert any("short" in imp.lower() or "content" in imp.lower() for imp in improvements)


def test_generate_improvements_good_episode_minimal(service, good_metrics):
    """Good episode should produce few or no improvements."""
    improvements = service.generate_improvements(good_metrics)
    # A good episode shouldn't have many improvement suggestions
    assert len(improvements) <= 2


# ============================================================================
# GENERATE_INTERPRETATION TESTS
# ============================================================================

def test_generate_interpretation_good_metrics(service, good_metrics):
    scores = service.calculate_quality_scores(good_metrics)
    interp = service.generate_interpretation(good_metrics, scores)
    assert interp.overall_rating in {"good", "excellent"}
    assert isinstance(interp.strengths, list)
    assert isinstance(interp.improvements, list)
    assert interp.recommendations is not None


def test_generate_interpretation_poor_metrics(service, poor_metrics):
    scores = service.calculate_quality_scores(poor_metrics)
    interp = service.generate_interpretation(poor_metrics, scores)
    assert interp.overall_rating in {"poor", "fair"}


def test_generate_interpretation_excellent_recommendation(service):
    """Excellent episode should get positive recommendation text."""
    metrics = QualityMetricsData(
        total_words=5000,
        duration_estimate_minutes=33.3,
        coherence_score=0.95,
        tone="casual",
        speaker_balance_ratio=1.0,
        is_balanced=True,
        max_monologue_words=80,
        dialogue_turns=60,
        has_good_banter=True,
    )
    scores = service.calculate_quality_scores(metrics)
    interp = service.generate_interpretation(metrics, scores)
    assert interp.overall_rating == "excellent"
    assert "outstanding" in interp.recommendations.lower()
