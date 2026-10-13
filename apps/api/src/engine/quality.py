"""Quality metrics computed from a script's structured turns (#570).

The definitions are the ones the removed podcastfy-XML calculator used (#540),
but the turns are read as given: consecutive turns by one speaker are one
monologue, where the XML parser had to assume strict alternation.
"""
import re
import statistics
from collections import Counter
from typing import Any, Dict, Optional

from .models import Script

WORDS_PER_MINUTE = 150.0

TONE_KEYWORDS = {
    "casual": {"yeah", "cool", "awesome", "hey", "stuff", "thing", "kinda", "gonna"},
    "academic": {"furthermore", "hypothesis", "research", "analysis", "demonstrate", "conclude", "evidence"},
    "humorous": {"haha", "lol", "funny", "joke", "hilarious", "kidding", "pun"},
}

_WORD = re.compile(r"[a-z']+")


def quality_metrics(script: Script) -> Dict[str, Any]:
    """The raw metrics stored in ``generation_progress["quality_metrics"]``."""
    lengths = [len(turn.text.split()) for turn in script.turns]
    total_words = sum(lengths)
    turns, max_monologue = _turn_taking(script, lengths)
    ratio = _balance_ratio(script, lengths)
    return {
        "total_words": total_words,
        "duration_estimate_minutes": round(total_words / WORDS_PER_MINUTE, 2),
        "coherence_score": _coherence(lengths),
        "tone": _tone(script),
        "speaker_balance_ratio": ratio,
        "is_balanced": ratio is not None and 0.3 <= ratio <= 3.33,
        "max_monologue_words": max_monologue,
        "dialogue_turns": turns,
        "has_good_banter": max_monologue <= 200 and turns >= 5,
    }


def _turn_taking(script: Script, lengths: list) -> tuple:
    """Speaker changes, and the most words spoken without one."""
    changes = longest = run = 0
    previous = None
    for turn, words in zip(script.turns, lengths):
        if turn.speaker == previous:
            run += words
        else:
            changes += previous is not None
            run = words
        previous = turn.speaker
        longest = max(longest, run)
    return changes, longest


def _balance_ratio(script: Script, lengths: list) -> Optional[float]:
    """Host words over guest words; None when the guest never speaks."""
    spoken = Counter()
    for turn, words in zip(script.turns, lengths):
        spoken[turn.speaker] += words
    return round(spoken["host"] / spoken["guest"], 2) if spoken["guest"] else None


def _coherence(lengths: list) -> float:
    """0.5 plus half the turn lengths' coefficient of variation, capped at 1."""
    if len(lengths) < 2:
        return 0.5
    mean = statistics.mean(lengths)
    if mean == 0:
        return 0.2
    return round(min(1.0, statistics.stdev(lengths) / mean * 0.5 + 0.5), 2)


def _tone(script: Script) -> str:
    """The tone whose keywords occur most as whole words; casual wins ties."""
    words = Counter(_WORD.findall(" ".join(t.text for t in script.turns).lower()))
    counts = {tone: sum(words[w] for w in keywords) for tone, keywords in TONE_KEYWORDS.items()}
    return max(counts, key=lambda tone: counts[tone])  # dict order puts casual first on ties
