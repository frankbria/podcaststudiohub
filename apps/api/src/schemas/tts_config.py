"""
TTS Configuration schemas for request/response validation.

Defines Pydantic models for TTSConfiguration CRUD operations with
provider-specific config validation and pagination support.
"""

import re
from pydantic import BaseModel, Field, field_validator, model_validator
from uuid import UUID
from datetime import datetime
from typing import Optional, Any

VALID_PROVIDERS = {"openai", "elevenlabs", "gemini", "gemini_multi", "edge"}

OPENAI_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
OPENAI_MODELS = {"tts-1", "tts-1-hd"}

ELEVENLABS_MODELS = {"eleven_multilingual_v2", "eleven_monolingual_v1", "eleven_turbo_v2"}

RATE_VOLUME_PATTERN = re.compile(r'^[+-]\d+%$')


def _validate_openai_config(config: dict) -> dict:
	"""Validate OpenAI TTS config fields."""
	for field in ("model", "voice_1", "voice_2"):
		if field not in config:
			raise ValueError(f"OpenAI config missing required field: '{field}'")
	if config["model"] not in OPENAI_MODELS:
		raise ValueError(f"OpenAI model must be one of {sorted(OPENAI_MODELS)}, got: '{config['model']}'")
	for voice_field in ("voice_1", "voice_2"):
		if config[voice_field] not in OPENAI_VOICES:
			raise ValueError(
				f"OpenAI {voice_field} must be one of {sorted(OPENAI_VOICES)}, got: '{config[voice_field]}'"
			)
	if "speed" in config:
		speed = config["speed"]
		if not isinstance(speed, (int, float)) or not (0.25 <= speed <= 4.0):
			raise ValueError(f"Voice speed must be between 0.25 and 4.0, got: {speed}")
	return config


def _validate_elevenlabs_config(config: dict) -> dict:
	"""Validate ElevenLabs TTS config fields."""
	for field in ("model", "voice_1_id", "voice_2_id"):
		if field not in config:
			raise ValueError(f"ElevenLabs config missing required field: '{field}'")
	if not isinstance(config["voice_1_id"], str) or not config["voice_1_id"].strip():
		raise ValueError("ElevenLabs voice_1_id must be a non-empty string")
	if not isinstance(config["voice_2_id"], str) or not config["voice_2_id"].strip():
		raise ValueError("ElevenLabs voice_2_id must be a non-empty string")
	for opt_field in ("stability", "similarity_boost"):
		if opt_field in config:
			val = config[opt_field]
			if not isinstance(val, (int, float)) or not (0.0 <= val <= 1.0):
				raise ValueError(f"ElevenLabs {opt_field} must be between 0.0 and 1.0, got: {val}")
	return config


def _validate_gemini_config(config: dict) -> dict:
	"""Validate Gemini / Gemini Multi TTS config fields."""
	for field in ("model", "language_code"):
		if field not in config:
			raise ValueError(f"Gemini config missing required field: '{field}'")
	if not isinstance(config["model"], str) or not config["model"].strip():
		raise ValueError("Gemini model must be a non-empty string")
	if not isinstance(config["language_code"], str) or not config["language_code"].strip():
		raise ValueError("Gemini language_code must be a non-empty string")
	return config


def _validate_edge_config(config: dict) -> dict:
	"""Validate Edge TTS config fields."""
	for field in ("voice_1", "voice_2"):
		if field not in config:
			raise ValueError(f"Edge TTS config missing required field: '{field}'")
	if not isinstance(config["voice_1"], str) or not config["voice_1"].strip():
		raise ValueError("Edge TTS voice_1 must be a non-empty string")
	if not isinstance(config["voice_2"], str) or not config["voice_2"].strip():
		raise ValueError("Edge TTS voice_2 must be a non-empty string")
	for opt_field in ("rate", "volume"):
		if opt_field in config:
			val = config[opt_field]
			if not isinstance(val, str) or not RATE_VOLUME_PATTERN.match(val):
				raise ValueError(
					f"Edge TTS {opt_field} must be in format '+N%' or '-N%', got: '{val}'"
				)
	return config


def validate_provider_config(provider: str, config: dict) -> dict:
	"""Validate provider-specific config fields."""
	validators = {
		"openai": _validate_openai_config,
		"elevenlabs": _validate_elevenlabs_config,
		"gemini": _validate_gemini_config,
		"gemini_multi": _validate_gemini_config,
		"edge": _validate_edge_config,
	}
	if provider in validators:
		return validators[provider](config)
	return config


class TTSConfigurationCreate(BaseModel):
	"""Schema for creating a new TTS configuration."""

	name: str = Field(
		...,
		min_length=1,
		max_length=255,
		description="Configuration name"
	)
	provider: str = Field(
		...,
		description="TTS provider type: openai, elevenlabs, gemini, gemini_multi, edge"
	)
	config: dict[str, Any] = Field(
		...,
		description="Provider-specific configuration"
	)
	is_default: bool = Field(
		False,
		description="Whether this is the default configuration"
	)

	@field_validator("provider")
	@classmethod
	def validate_provider(cls, v: str) -> str:
		if v not in VALID_PROVIDERS:
			raise ValueError(f"Invalid provider type: '{v}'. Must be one of {sorted(VALID_PROVIDERS)}")
		return v

	@model_validator(mode="after")
	def validate_config_for_provider(self) -> "TTSConfigurationCreate":
		validate_provider_config(self.provider, self.config)
		return self


class TTSConfigurationUpdate(BaseModel):
	"""Schema for updating an existing TTS configuration. All fields optional."""

	name: Optional[str] = Field(
		None,
		min_length=1,
		max_length=255,
		description="Configuration name"
	)
	provider: Optional[str] = Field(
		None,
		description="TTS provider type"
	)
	config: Optional[dict[str, Any]] = Field(
		None,
		description="Provider-specific configuration"
	)
	is_default: Optional[bool] = Field(
		None,
		description="Whether this is the default configuration"
	)

	@field_validator("provider")
	@classmethod
	def validate_provider(cls, v: Optional[str]) -> Optional[str]:
		if v is not None and v not in VALID_PROVIDERS:
			raise ValueError(f"Invalid provider type: '{v}'. Must be one of {sorted(VALID_PROVIDERS)}")
		return v

	@model_validator(mode="after")
	def validate_config_for_provider(self) -> "TTSConfigurationUpdate":
		if self.config is not None and self.provider is not None:
			validate_provider_config(self.provider, self.config)
		return self


class TTSConfigurationResponse(BaseModel):
	"""Schema for TTS configuration response data."""

	id: UUID
	user_id: UUID
	tenant_id: UUID
	name: str
	provider: str
	config: dict[str, Any]
	is_default: bool
	created_at: datetime
	updated_at: datetime

	model_config = {"from_attributes": True}


class TTSConfigurationListResponse(BaseModel):
	"""Schema for paginated TTS configuration list response."""

	tts_configs: list[TTSConfigurationResponse]
	total: int = Field(..., description="Total count of configurations")
	page: int = Field(..., description="Current page number")
	page_size: int = Field(..., description="Items per page")
	total_pages: int = Field(..., description="Total number of pages")
