"""Quality metrics computed from the engine's structured turns (#570)."""
import pytest

from src.engine.models import Script
from src.engine.quality import quality_metrics
from src.schemas.quality_metrics import QualityMetricsData


def _script(*turns):
    return Script(title="t", summary="s", turns=[{"speaker": s, "text": t} for s, t in turns])


def test_counts_come_from_the_turns_not_a_reconstructed_order():
    """Two host turns in a row are one monologue and no speaker change; the
    old XML parser assumed strict alternation and got both wrong."""
    metrics = quality_metrics(_script(
        ("host", "one two three"),
        ("host", "four five"),
        ("guest", "six"),
        ("host", "seven eight"),
    ))

    assert metrics["total_words"] == 8
    assert metrics["dialogue_turns"] == 2
    assert metrics["max_monologue_words"] == 5
    assert metrics["speaker_balance_ratio"] == 7.0
    assert metrics["is_balanced"] is False


def test_duration_assumes_150_words_a_minute():
    metrics = quality_metrics(_script(("host", "word " * 300), ("guest", "word " * 150)))

    assert metrics["duration_estimate_minutes"] == 3.0


def test_banter_needs_five_changes_and_no_monologue_over_200_words():
    lively = [("host", "a b"), ("guest", "c d")] * 3  # five changes
    assert quality_metrics(_script(*lively))["has_good_banter"] is True
    assert quality_metrics(_script(*lively[:5]))["has_good_banter"] is False
    assert quality_metrics(_script(*lively, ("guest", "w " * 199)))["has_good_banter"] is False


def test_a_single_speaker_script_has_no_ratio_and_still_stores():
    """The old ratio was float('inf'), which JSONB cannot hold."""
    metrics = quality_metrics(_script(("host", "only me"), ("host", "still me")))

    assert metrics["speaker_balance_ratio"] is None
    assert metrics["is_balanced"] is False
    QualityMetricsData(**metrics)  # the read surface accepts it


@pytest.mark.parametrize(
    ("text", "tone"),
    [
        ("Furthermore the research and analysis demonstrate it.", "academic"),
        ("Haha that joke was hilarious, lol.", "humorous"),
        ("Yeah that is cool stuff.", "casual"),
        # Substrings must not count: "punishment" is not "pun" (a substring count
        # would call this humorous; no tone word appears, so the default holds).
        ("Punishment, a pundit, punctually.", "casual"),
    ],
)
def test_tone_counts_whole_words(text, tone):
    assert quality_metrics(_script(("host", text), ("guest", "ok")))["tone"] == tone


def test_coherence_rewards_varied_turn_lengths():
    flat = quality_metrics(_script(("host", "a b c"), ("guest", "d e f")))
    varied = quality_metrics(_script(("host", "a"), ("guest", "b c d e f g h i j")))

    assert flat["coherence_score"] == 0.5
    assert varied["coherence_score"] > 0.8
    assert quality_metrics(_script(("host", "alone")))["coherence_score"] == 0.5
    assert quality_metrics(_script(("host", ""), ("guest", "")))["coherence_score"] == 0.2


def test_every_metric_satisfies_the_read_schema():
    metrics = quality_metrics(_script(("host", "Welcome back."), ("guest", "Glad to be here.")))

    assert set(metrics) == set(QualityMetricsData.model_fields)
    QualityMetricsData(**metrics)
