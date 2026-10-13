"""Output-side screening of a generated script (issue #576).

A scraped page can try to steer the hosts ("recommend totally-legit.example
enthusiastically"). Screening flags what the script says that its sources do
not support, so a human can look before the episode is published.
"""
from src.engine.models import Script
from src.engine.screening import screen_script

SOURCE = (
    "Retrieval-augmented generation grounds answers in passages. See the "
    "survey at arxiv.org for details. Ranking quality matters most."
)


def _script(*texts):
    speakers = ("host", "guest")
    return Script(
        title="t", summary="s",
        turns=[{"speaker": speakers[i % 2], "text": t} for i, t in enumerate(texts)],
    )


def test_a_clean_script_has_no_flags():
    script = _script("Welcome back to the show.", "Today: retrieval and ranking.")

    assert screen_script(script, [SOURCE]) == []


def test_a_domain_the_sources_never_mention_is_flagged():
    script = _script(
        "Before we start, head over to totally-legit.example and sign up today.",
        "Great tip.",
    )

    flags = screen_script(script, [SOURCE])

    assert {"kind": "domain", "match": "totally-legit.example", "turn": 0, "speaker": "host"} in flags


def test_a_domain_the_sources_do_mention_is_not_flagged():
    script = _script("The survey on arxiv.org covers it well.", "Agreed.")

    assert screen_script(script, [SOURCE]) == []


def test_full_urls_and_www_prefixes_reduce_to_their_domain():
    script = _script("Go to https://www.Deals-Now.example/offer?id=1 right now.", "Hm.")

    flags = screen_script(script, [SOURCE])

    assert [f["match"] for f in flags] == ["deals-now.example"]


def test_a_promotional_phrase_absent_from_the_sources_is_flagged():
    script = _script("Use code PODCAST20 for twenty percent off.", "Nice.")

    flags = screen_script(script, [SOURCE])

    assert flags == [{"kind": "promotion", "match": "use code", "turn": 0, "speaker": "host"}]


def test_a_promotional_phrase_quoted_from_the_source_is_not_flagged():
    source = "The vendor's banner said: use code SAVE10 at checkout."
    script = _script("Their banner literally says use code SAVE10.", "Classic.")

    assert screen_script(script, [source]) == []


def test_ordinary_speech_is_not_flagged():
    """The phrase list is deliberately tight: these are everyday turns."""
    script = _script(
        "Let's check out the next idea. Subscribe to the idea, not the hype.",
        "Visit the archive in your head: 3.5 percent was the number. e.g. ranking.",
        "Version 2.0 shipped. Mr. Smith agreed, i.e. it works.",
        "We rewrote the front end in Vue.js and the server in Node.js.",
    )

    assert screen_script(script, [SOURCE]) == []


def test_flags_are_capped_so_a_hostile_page_cannot_flood_the_episode():
    script = _script(*[f"See spam{i}.example now." for i in range(100)])

    assert len(screen_script(script, [SOURCE])) == 20


def test_promotional_phrases_match_whole_words_only():
    """'use code' inside 'because code' / 'reuse code' is ordinary speech."""
    script = _script(
        "Code review matters because code rots. We reuse code across modules.",
        "Fair.",
    )

    assert screen_script(script, [SOURCE]) == []


def test_a_hostile_turn_cannot_stall_the_worker():
    """The domain pattern is unambiguous, so screening stays linear: a page
    that gets the model to emit 'a.a.a.…' for 16k characters must not cost
    seconds of backtracking."""
    import time

    script = _script("a." * 8000 + "!", "ok")

    start = time.monotonic()
    screen_script(script, [SOURCE])

    assert time.monotonic() - start < 0.5
