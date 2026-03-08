"""
Pydantic schemas for TTS configuration request/response validation.

Provides schemas for creating, updating, and retrieving TTS configurations
with provider-specific validation for OpenAI, ElevenLabs, Gemini, and Edge TTS.
"""

from datetime import datetime
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict, ValidationInfo
from uuid import UUID


# Supported TTS providers
TTSProvider = Literal['openai', 'elevenlabs', 'gemini', 'gemini_multi', 'edge']


class TTSConfigCreate(BaseModel):
    """Schema for creating a TTS configuration."""

    name: str = Field(..., min_length=1, max_length=255, description="Display name for this TTS configuration")
    provider: TTSProvider = Field(..., description="TTS provider (openai, elevenlabs, gemini, gemini_multi, edge)")
    config: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific configuration")
    is_default: bool = Field(False, description="Whether this is the default TTS configuration")

    @field_validator('config')
    @classmethod
    def validate_config(cls, v: Dict[str, Any], info: ValidationInfo) -> Dict[str, Any]:
        """Validate config structure based on provider."""
        provider = info.data.get('provider')

        if provider == 'openai':
            # Optional fields with defaults
            v.setdefault('model', 'tts-1-hd')
            v.setdefault('voice_1', 'alloy')
            v.setdefault('voice_2', 'echo')

        elif provider == 'elevenlabs':
            v.setdefault('model', 'eleven_multilingual_v2')

        elif provider in ('gemini', 'gemini_multi'):
            v.setdefault('model', 'en-US-Studio-MultiSpeaker')
            v.setdefault('language_code', 'en-US')

        elif provider == 'edge':
            v.setdefault('voice_1', 'en-US-AriaNeural')
            v.setdefault('voice_2', 'en-US-GuyNeural')

        return v

    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "name": "OpenAI Default",
                "provider": "openai",
                "config": {
                    "model": "tts-1-hd",
                    "voice_1": "alloy",
                    "voice_2": "echo"
                },
                "is_default": True
            },
            {
                "name": "ElevenLabs Premium",
                "provider": "elevenlabs",
                "config": {
                    "model": "eleven_multilingual_v2",
                    "voice_1_id": "21m00Tcm4TlvDq8ikWAM",
                    "voice_2_id": "AZnzlk1XvdvUeBnXmlld"
                },
                "is_default": False
            }
        ]
    })


class TTSConfigUpdate(BaseModel):
    """Schema for updating a TTS configuration. All fields optional."""

    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Display name")
    config: Optional[Dict[str, Any]] = Field(None, description="Provider-specific configuration")
    is_default: Optional[bool] = Field(None, description="Whether this is the default TTS configuration")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "name": "Updated OpenAI Config",
            "config": {"voice_1": "nova"},
            "is_default": True
        }
    })


class TTSConfigResponse(BaseModel):
    """Schema for TTS configuration response."""

    id: UUID
    user_id: UUID
    tenant_id: UUID
    name: str
    provider: str
    config: Dict[str, Any]
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TTSConfigListResponse(BaseModel):
    """Schema for paginated TTS configuration list response."""

    tts_configs: list[TTSConfigResponse]
    total: int = Field(..., description="Total number of configurations")
    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(..., ge=1, le=100, description="Number of items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")
