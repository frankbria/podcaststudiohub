"""
Conversation template schemas for request/response validation.

Defines Pydantic models for ConversationTemplate CRUD operations with
config structure validation and pagination support.
"""

from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional, List


VALID_CONVERSATION_STYLES = {"casual", "formal", "humorous", "educational", "technical", "storytelling"}
VALID_ENGAGEMENT_TECHNIQUES = {
	"rhetorical questions",
	"anecdotes",
	"listener callouts",
	"humor",
	"metaphors",
	"statistics",
	"expert quotes",
}


class ConversationTemplateConfig(BaseModel):
	"""Schema for the conversation template config JSONB field."""

	# Required fields
	word_count: int = Field(
		...,
		ge=100,
		le=5000,
		description="Target word count for transcript (100-5000)"
	)
	conversation_style: List[str] = Field(
		...,
		min_length=1,
		description="List of conversation styles (1-5 values)"
	)
	roles_person1: str = Field(
		...,
		min_length=1,
		max_length=100,
		description="Role of first speaker"
	)
	roles_person2: str = Field(
		...,
		min_length=1,
		max_length=100,
		description="Role of second speaker"
	)
	dialogue_structure: List[str] = Field(
		...,
		description="Ordered list of dialogue sections (2-10)"
	)
	podcast_name: str = Field(
		...,
		min_length=1,
		max_length=255,
		description="Podcast title"
	)
	output_language: str = Field(
		...,
		min_length=2,
		max_length=10,
		description="Language code (e.g. 'en', 'es', 'fr')"
	)
	creativity: float = Field(
		...,
		ge=0.0,
		le=1.0,
		description="LLM creativity parameter (0.0-1.0)"
	)

	# Optional fields
	podcast_tagline: Optional[str] = Field(
		None,
		max_length=255,
		description="Podcast tagline/subtitle"
	)
	engagement_techniques: Optional[List[str]] = Field(
		None,
		description="List of engagement techniques"
	)

	@field_validator('conversation_style')
	@classmethod
	def validate_conversation_style(cls, v: List[str]) -> List[str]:
		"""Validate conversation style values and count."""
		if len(v) == 0:
			raise ValueError("conversation_style must have at least 1 value")
		if len(v) > 5:
			raise ValueError(f"conversation_style can have at most 5 values, got {len(v)}")
		invalid = set(v) - VALID_CONVERSATION_STYLES
		if invalid:
			valid_str = ", ".join(sorted(VALID_CONVERSATION_STYLES))
			raise ValueError(
				f"conversation_style contains invalid value(s): {', '.join(repr(s) for s in sorted(invalid))} "
				f"(valid: {valid_str})"
			)
		return v

	@field_validator('dialogue_structure')
	@classmethod
	def validate_dialogue_structure(cls, v: List[str]) -> List[str]:
		"""Validate dialogue structure has 2-10 sections."""
		if len(v) < 2:
			raise ValueError(f"dialogue_structure must have at least 2 sections, got {len(v)}")
		if len(v) > 10:
			raise ValueError(f"dialogue_structure can have at most 10 sections, got {len(v)}")
		for i, section in enumerate(v):
			if not section.strip():
				raise ValueError(f"dialogue_structure section {i} must not be empty")
		return v

	@field_validator('engagement_techniques')
	@classmethod
	def validate_engagement_techniques(cls, v: Optional[List[str]]) -> Optional[List[str]]:
		"""Validate engagement technique values."""
		if v is None:
			return v
		invalid = set(v) - VALID_ENGAGEMENT_TECHNIQUES
		if invalid:
			valid_str = ", ".join(sorted(VALID_ENGAGEMENT_TECHNIQUES))
			raise ValueError(
				f"engagement_techniques contains invalid value(s): {', '.join(repr(s) for s in sorted(invalid))} "
				f"(valid: {valid_str})"
			)
		return v


class ConversationTemplateCreate(BaseModel):
	"""Schema for creating a new conversation template."""

	name: str = Field(
		...,
		min_length=1,
		max_length=255,
		description="Template name"
	)
	description: Optional[str] = Field(
		None,
		description="Template description"
	)
	config: ConversationTemplateConfig = Field(
		...,
		description="Conversation configuration"
	)
	is_default: bool = Field(
		False,
		description="Whether this is the default template"
	)


class ConversationTemplateUpdate(BaseModel):
	"""Schema for updating an existing conversation template. All fields optional."""

	name: Optional[str] = Field(
		None,
		min_length=1,
		max_length=255,
		description="Template name"
	)
	description: Optional[str] = Field(
		None,
		description="Template description"
	)
	config: Optional[ConversationTemplateConfig] = Field(
		None,
		description="Conversation configuration"
	)
	is_default: Optional[bool] = Field(
		None,
		description="Whether this is the default template"
	)


class ConversationTemplateResponse(BaseModel):
	"""Schema for conversation template response data."""

	id: UUID
	user_id: UUID
	tenant_id: UUID
	name: str
	description: Optional[str]
	config: dict
	is_default: bool
	created_at: datetime
	updated_at: datetime

	model_config = {"from_attributes": True}


class ConversationTemplateListResponse(BaseModel):
	"""Schema for paginated conversation template list response."""

	templates: List[ConversationTemplateResponse]
	total: int = Field(..., description="Total count of templates")
	page: int = Field(..., description="Current page number")
	page_size: int = Field(..., description="Items per page")
	total_pages: int = Field(..., description="Total number of pages")
