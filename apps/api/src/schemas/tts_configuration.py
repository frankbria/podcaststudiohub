"""
TTS configuration schemas for request/response validation.

Defines Pydantic models for TTSConfiguration CRUD operations with
provider-specific config validation and pagination support.
"""

from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Literal


VALID_PROVIDERS = {"openai", "elevenlabs", "gemini", "gemini_multi", "edge"}

OPENAI_REQUIRED_KEYS = {"model", "voice_1", "voice_2"}
ELEVENLABS_REQUIRED_KEYS = {"model", "voice_1_id", "voice_2_id"}
GEMINI_REQUIRED_KEYS = {"model", "language_code"}
EDGE_REQUIRED_KEYS = {"voice_1", "voice_2"}

PROVIDER_REQUIRED_KEYS = {
	"openai": OPENAI_REQUIRED_KEYS,
	"elevenlabs": ELEVENLABS_REQUIRED_KEYS,
	"gemini": GEMINI_REQUIRED_KEYS,
	"gemini_multi": GEMINI_REQUIRED_KEYS,
	"edge": EDGE_REQUIRED_KEYS,
}


def _validate_provider_config(provider: str, config: dict) -> dict:
	"""Validate config dict against provider-specific required keys."""
	required = PROVIDER_REQUIRED_KEYS.get(provider)
	if required is None:
		raise ValueError(f"Invalid provider type: '{provider}'")
	missing = required - set(config.keys())
	if missing:
		missing_str = ", ".join(f"'{k}'" for k in sorted(missing))
		raise ValueError(
			f"{provider.capitalize()} config missing required field(s): {missing_str}"
		)
	# Provider-specific range validation
	if provider == "openai":
		speed = config.get("speed")
		if speed is not None and not (0.25 <= float(speed) <= 4.0):
			raise ValueError(
				f"Voice speed must be between 0.25 and 4.0, got: {speed}"
			)
	if provider == "elevenlabs":
		stability = config.get("stability")
		if stability is not None and not (0.0 <= float(stability) <= 1.0):
			raise ValueError(
				f"Stability must be between 0.0 and 1.0, got: {stability}"
			)
		similarity_boost = config.get("similarity_boost")
		if similarity_boost is not None and not (0.0 <= float(similarity_boost) <= 1.0):
			raise ValueError(
				f"Similarity boost must be between 0.0 and 1.0, got: {similarity_boost}"
			)
		# Key-presence alone isn't enough: empty/whitespace/null voice IDs produce
		# a non-functional config. Require real, non-empty string values (#221).
		for key in ("voice_1_id", "voice_2_id"):
			value = config.get(key)
			if not isinstance(value, str) or not value.strip():
				raise ValueError(
					"ElevenLabs config requires non-empty voice_1_id and voice_2_id"
				)
	return config


class TTSConfigCreate(BaseModel):
	"""Schema for creating a new TTS configuration."""

	name: str = Field(
		...,
		min_length=1,
		max_length=255,
		description="Configuration name"
	)
	provider: Literal["openai", "elevenlabs", "gemini", "gemini_multi", "edge"] = Field(
		...,
		description="TTS provider type"
	)
	config: dict = Field(
		...,
		description="Provider-specific configuration"
	)
	is_default: bool = Field(
		False,
		description="Whether this is the default TTS configuration"
	)

	@field_validator("config")
	@classmethod
	def validate_config(cls, v: dict, info) -> dict:
		"""Validate config keys based on provider."""
		provider = info.data.get("provider")
		if provider is None:
			# Provider validation failed separately; skip config check
			return v
		return _validate_provider_config(provider, v)


class TTSConfigUpdate(BaseModel):
	"""Schema for updating a TTS configuration. All fields optional."""

	name: Optional[str] = Field(
		None,
		min_length=1,
		max_length=255,
		description="Configuration name"
	)
	provider: Optional[Literal["openai", "elevenlabs", "gemini", "gemini_multi", "edge"]] = Field(
		None,
		description="TTS provider type"
	)
	config: Optional[dict] = Field(
		None,
		description="Provider-specific configuration"
	)
	is_default: Optional[bool] = Field(
		None,
		description="Whether this is the default TTS configuration"
	)

	@field_validator("config")
	@classmethod
	def validate_config(cls, v: Optional[dict], info) -> Optional[dict]:
		"""Validate config keys based on provider when both are provided."""
		if v is None:
			return v
		provider = info.data.get("provider")
		if provider is None:
			# Can't validate without provider; accept the dict as-is
			return v
		return _validate_provider_config(provider, v)


class TTSConfigResponse(BaseModel):
	"""Schema for TTS configuration response data."""

	id: UUID
	user_id: UUID
	tenant_id: UUID
	name: str
	provider: str
	config: dict
	is_default: bool
	created_at: datetime
	updated_at: datetime

	model_config = {"from_attributes": True}


class TTSConfigListResponse(BaseModel):
	"""Schema for paginated TTS configuration list response."""

	configs: List[TTSConfigResponse]
	total: int = Field(..., description="Total count of configurations")
	page: int = Field(..., description="Current page number")
	page_size: int = Field(..., description="Items per page")
	total_pages: int = Field(..., description="Total number of pages")
