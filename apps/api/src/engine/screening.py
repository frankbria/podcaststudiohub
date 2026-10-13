"""Flag what a generated script says that its sources do not support (#576).

The script is written from scraped pages and uploads, so a hostile source can
try to make the hosts endorse a site or read out a discount code. The prompts
already tell the model to treat sources as data (#541); this is the output-side
check that does not rely on the model obeying.

Two signals, both judged against the source text itself:

* a **domain** spoken in the script that no source mentions;
* a **promotional phrase** from a deliberately tight list that no source uses.

The list is tight on purpose: flags hold an episode back from publication, so
everyday turns ("check out this idea", "subscribe to the theory") must never
trip it. Flags are capped so a hostile page cannot flood the episode record.
"""
import re
from typing import Dict, List, Sequence

from src.engine.models import Script

MAX_FLAGS = 20

# Final labels that make "word.word" a domain. A closed set rather than "any
# two letters": spoken tech names like Node.js or Vue.js would otherwise flag
# every engineering episode. (A name that is also a real domain, like ASP.NET,
# can still match; the source check clears it whenever the source mentions it.)
# "example"/"test" are the RFC 2606 reserved names.
_TLDS = frozenset({
    "com", "net", "org", "io", "co", "ai", "app", "dev", "info", "biz", "xyz",
    "me", "tv", "shop", "store", "site", "online", "link", "click", "top",
    "us", "uk", "ca", "de", "fr", "eu", "au", "in", "example", "test",
})
# Matched against one whitespace token at a time with fullmatch, and labels
# cannot contain dots, so there is a single way to split a token: screening is
# linear even on a hostile "a.a.a.…" turn. Tokens longer than any real domain
# (253) plus a path are skipped outright.
_MAX_TOKEN = 300
_TOKEN_TRIM = ".,;:!?()[]{}<>\"'"
_DOMAIN = re.compile(r"(?:https?://)?(?:www\.)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?:[/?#]\S*)?")
# Whole words only: "because code" and "reuse code" are ordinary speech.
_PROMOTIONS = re.compile(
    r"\b(use code|promo code|discount code|coupon code|buy now|sponsored by"
    r"|affiliate link|limited-time offer)\b"
)


def screen_script(script: Script, sources: Sequence[str]) -> List[Dict]:
    """Return at most MAX_FLAGS flags, in script order; [] for a clean script."""
    source_text = " ".join(sources).lower()
    flags: List[Dict] = []
    for position, turn in enumerate(script.turns):
        for kind, match in _findings(turn.text):
            if match not in source_text:
                flags.append(
                    {"kind": kind, "match": match, "turn": position, "speaker": turn.speaker}
                )
    return flags[:MAX_FLAGS]


def _findings(text: str):
    lowered = text.lower()
    for token in lowered.split():
        domain = _domain_of(token.strip(_TOKEN_TRIM))
        if domain:
            yield "domain", domain
    for phrase in dict.fromkeys(_PROMOTIONS.findall(lowered)):
        yield "promotion", phrase


def _domain_of(token: str):
    if len(token) > _MAX_TOKEN:
        return None
    found = _DOMAIN.fullmatch(token)
    if found and found.group(1).rsplit(".", 1)[1] in _TLDS:
        return found.group(1)
    return None
