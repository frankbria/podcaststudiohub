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

    # Bounds mirror ConversationTemplateConfig, which already enforces them
    # at write time. Repeated here because creativity flows straight into the
    # provider's temperature: an out-of-range value should be a clean
    # validation error, not a 400 from the vendor mid-generation.
    word_count: int = Field(default=2000, ge=100, le=5000)
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
    creativity: float = Field(default=1.0, ge=0.0, le=1.0)
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
        """Build from the raw template JSONB (or ``None`` for no template).

        Nulls are dropped before validation. ``podcast_tagline`` and
        ``engagement_techniques`` are optional in ``ConversationTemplateConfig``,
        and the write path dumps with ``exclude_none=False``
        (``conversation_template_service.py:46``), so a template saved without
        them is stored with explicit JSON nulls. Pydantic does not fall back to
        a default for an explicit ``None``, so passing them straight through
        would reject the stored shape instead of using the defaults below.
        """
        return cls.model_validate(
            {key: value for key, value in (config or {}).items() if value is not None}
        )
