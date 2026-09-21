"""Prompt templates, versioned in git alongside the code that uses them.

podcastfy fetched its prompts from a third-party LangChain Hub account on every
generation (``content_generator.py:790``) — an outbound call on the paid path,
the one reachable advisory in #446, and a silent dependency on someone else's
account staying up. These are files.

The substance is ported from the four commit-pinned templates listed in
``docs/podcastfy-advisory-reachability.md``; the output-format sections are not,
because those asked for ``<Person1>`` free text and we ask for a JSON schema.
"""
from importlib.resources import files

_SUFFIX = ".md"


def load(name: str) -> str:
    """Return the named prompt template's raw text."""
    return files(__package__).joinpath(name + _SUFFIX).read_text(encoding="utf-8")
