"""Structured types for the in-repo generation engine (issue #541).

``Script`` is the contract between the script layer and everything downstream:
TTS (#542), persistence, and the quality surface (#540). It replaces podcastfy's
regex-parsed ``<Person1>``/``<Person2>`` free text, where a malformed tag
silently dropped a turn and nothing downstream could tell.
"""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Speaker = Literal["host", "guest"]


class Turn(BaseModel):
    """One speaker's uninterrupted contribution to the conversation."""

    speaker: Speaker
    text: str


class Script(BaseModel):
    """A complete, ordered podcast conversation.

    Doubles as the provider response schema: both the Gemini and OpenAI
    structured-output APIs are handed this model directly, so the shape the
    model is asked for and the shape the rest of the app consumes cannot drift
    apart. That means no ``Optional`` fields and no defaults here — strict
    structured-output modes require every property to be required.
    """

    title: str
    summary: str
    turns: List[Turn]


class ConversationConfig(BaseModel):
    """Script-layer settings, mapped from ``conversation_templates.config``.

    That JSONB column keeps its existing shape (the router's merge at
    ``src/routers/generation.py:205-234`` is untouched), so the dict arriving
    here also carries keys that belong to the TTS layer — ``text_to_speech``,
    ``output_directories``. ``extra="ignore"`` drops them rather than making the
    router pre-filter.

    Every field has a default: an episode with neither a template nor a project
    default sends ``None``, and the engine still has to produce a script.
    Defaults match podcastfy's shipped ``conversation_config.yaml`` so the
    no-template output stays recognisable after the cut-over (#543).
    """

    model_config = ConfigDict(extra="ignore")

    word_count: int = 2000
    conversation_style: List[str] = Field(
        default_factory=lambda: ["engaging", "fast-paced", "enthusiastic"]
    )
    roles_person1: str = "main summarizer"
    roles_person2: str = "questioner/clarifier"
    dialogue_structure: List[str] = Field(
        default_factory=lambda: ["Introduction", "Main Content", "Conclusion"]
    )
    podcast_name: str = "PODCASTIFY"
    podcast_tagline: str = "Your Personal Generative AI Podcast"
    output_language: str = "English"
    creativity: float = 1.0
    engagement_techniques: List[str] = Field(
        default_factory=lambda: [
            "rhetorical questions",
            "anecdotes",
            "analogies",
            "humor",
        ]
    )

    @classmethod
    def from_template_config(
        cls, config: Optional[Dict[str, Any]]
    ) -> "ConversationConfig":
        """Build from the raw template JSONB (or ``None`` for no template)."""
        return cls.model_validate(config or {})
