"""
Unit tests for TTS Configuration schema validation.

Tests Pydantic schema validation logic without requiring a database.
"""

import pytest
from pydantic import ValidationError

from src.schemas.tts_config import (
	TTSConfigurationCreate,
	TTSConfigurationUpdate,
	VALID_PROVIDERS,
)

VALID_OPENAI = {"model": "tts-1-hd", "voice_1": "alloy", "voice_2": "echo"}
VALID_ELEVENLABS = {
	"model": "eleven_multilingual_v2",
	"voice_1_id": "21m00Tcm4TlvDq8ikWAM",
	"voice_2_id": "AZnzlk1XvdvUeBnXmlld",
}
VALID_GEMINI = {"model": "en-US-Studio-MultiSpeaker", "language_code": "en-US"}
VALID_EDGE = {"voice_1": "en-US-AriaNeural", "voice_2": "en-US-GuyNeural"}


# ============================================================================
# TTSConfigurationCreate - Provider Validation
# ============================================================================

def test_valid_providers_accepted():
	"""All valid providers are accepted."""
	for provider in VALID_PROVIDERS:
		config = VALID_GEMINI if provider in ("gemini", "gemini_multi") else (
			VALID_ELEVENLABS if provider == "elevenlabs" else (
				VALID_EDGE if provider == "edge" else VALID_OPENAI
			)
		)
		c = TTSConfigurationCreate(name="Test", provider=provider, config=config)
		assert c.provider == provider


def test_invalid_provider_rejected():
	"""Invalid provider is rejected with ValidationError."""
	with pytest.raises(ValidationError) as exc_info:
		TTSConfigurationCreate(name="Test", provider="invalid_provider", config={})
	assert "invalid" in str(exc_info.value).lower()


def test_empty_provider_rejected():
	"""Empty string provider is rejected."""
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="", config=VALID_OPENAI)


# ============================================================================
# TTSConfigurationCreate - Name Validation
# ============================================================================

def test_valid_name_accepted():
	"""Normal name is accepted."""
	c = TTSConfigurationCreate(name="My Config", provider="openai", config=VALID_OPENAI)
	assert c.name == "My Config"


def test_empty_name_rejected():
	"""Empty name is rejected."""
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="", provider="openai", config=VALID_OPENAI)


def test_name_too_long_rejected():
	"""Name exceeding 255 chars is rejected."""
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="A" * 256, provider="openai", config=VALID_OPENAI)


def test_name_max_length_accepted():
	"""Name at exactly 255 chars is accepted."""
	c = TTSConfigurationCreate(name="A" * 255, provider="openai", config=VALID_OPENAI)
	assert len(c.name) == 255


# ============================================================================
# TTSConfigurationCreate - Default Flag
# ============================================================================

def test_is_default_defaults_to_false():
	"""is_default defaults to False."""
	c = TTSConfigurationCreate(name="Test", provider="openai", config=VALID_OPENAI)
	assert c.is_default is False


def test_is_default_can_be_set_true():
	"""is_default can be set to True."""
	c = TTSConfigurationCreate(name="Test", provider="openai", config=VALID_OPENAI, is_default=True)
	assert c.is_default is True


# ============================================================================
# OpenAI Config Validation
# ============================================================================

def test_openai_valid_config_accepted():
	"""Valid OpenAI config is accepted."""
	c = TTSConfigurationCreate(name="Test", provider="openai", config=VALID_OPENAI)
	assert c.config == VALID_OPENAI


def test_openai_with_speed_accepted():
	"""OpenAI config with valid speed is accepted."""
	config = {**VALID_OPENAI, "speed": 1.5}
	c = TTSConfigurationCreate(name="Test", provider="openai", config=config)
	assert c.config["speed"] == 1.5


def test_openai_missing_model_rejected():
	"""OpenAI config missing 'model' is rejected."""
	config = {"voice_1": "alloy", "voice_2": "echo"}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="openai", config=config)


def test_openai_missing_voice_1_rejected():
	"""OpenAI config missing 'voice_1' is rejected."""
	config = {"model": "tts-1-hd", "voice_2": "echo"}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="openai", config=config)


def test_openai_missing_voice_2_rejected():
	"""OpenAI config missing 'voice_2' is rejected."""
	config = {"model": "tts-1-hd", "voice_1": "alloy"}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="openai", config=config)


def test_openai_invalid_model_rejected():
	"""OpenAI config with invalid model is rejected."""
	config = {"model": "invalid-model", "voice_1": "alloy", "voice_2": "echo"}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="openai", config=config)


def test_openai_invalid_voice_rejected():
	"""OpenAI config with invalid voice is rejected."""
	config = {"model": "tts-1-hd", "voice_1": "not-a-voice", "voice_2": "echo"}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="openai", config=config)


def test_openai_speed_too_low_rejected():
	"""OpenAI config with speed below 0.25 is rejected."""
	config = {**VALID_OPENAI, "speed": 0.1}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="openai", config=config)


def test_openai_speed_too_high_rejected():
	"""OpenAI config with speed above 4.0 is rejected."""
	config = {**VALID_OPENAI, "speed": 5.0}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="openai", config=config)


def test_openai_speed_min_boundary_accepted():
	"""OpenAI config with speed at 0.25 is accepted."""
	config = {**VALID_OPENAI, "speed": 0.25}
	c = TTSConfigurationCreate(name="Test", provider="openai", config=config)
	assert c.config["speed"] == 0.25


def test_openai_speed_max_boundary_accepted():
	"""OpenAI config with speed at 4.0 is accepted."""
	config = {**VALID_OPENAI, "speed": 4.0}
	c = TTSConfigurationCreate(name="Test", provider="openai", config=config)
	assert c.config["speed"] == 4.0


# ============================================================================
# ElevenLabs Config Validation
# ============================================================================

def test_elevenlabs_valid_config_accepted():
	"""Valid ElevenLabs config is accepted."""
	c = TTSConfigurationCreate(name="Test", provider="elevenlabs", config=VALID_ELEVENLABS)
	assert c.config == VALID_ELEVENLABS


def test_elevenlabs_missing_model_rejected():
	"""ElevenLabs config missing 'model' is rejected."""
	config = {"voice_1_id": "abc", "voice_2_id": "def"}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="elevenlabs", config=config)


def test_elevenlabs_missing_voice_1_id_rejected():
	"""ElevenLabs config missing 'voice_1_id' is rejected."""
	config = {"model": "eleven_multilingual_v2", "voice_2_id": "def"}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="elevenlabs", config=config)


def test_elevenlabs_stability_out_of_range_rejected():
	"""ElevenLabs config with stability > 1.0 is rejected."""
	config = {**VALID_ELEVENLABS, "stability": 1.5}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="elevenlabs", config=config)


def test_elevenlabs_stability_boundary_accepted():
	"""ElevenLabs config with stability at 0.0 and 1.0 is accepted."""
	for val in (0.0, 0.5, 1.0):
		config = {**VALID_ELEVENLABS, "stability": val}
		c = TTSConfigurationCreate(name="Test", provider="elevenlabs", config=config)
		assert c.config["stability"] == val


def test_elevenlabs_similarity_boost_out_of_range_rejected():
	"""ElevenLabs config with similarity_boost < 0.0 is rejected."""
	config = {**VALID_ELEVENLABS, "similarity_boost": -0.1}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="elevenlabs", config=config)


# ============================================================================
# Gemini / Gemini Multi Config Validation
# ============================================================================

def test_gemini_valid_config_accepted():
	"""Valid Gemini config is accepted."""
	c = TTSConfigurationCreate(name="Test", provider="gemini", config=VALID_GEMINI)
	assert c.config == VALID_GEMINI


def test_gemini_multi_valid_config_accepted():
	"""Valid Gemini Multi config is accepted."""
	c = TTSConfigurationCreate(name="Test", provider="gemini_multi", config=VALID_GEMINI)
	assert c.provider == "gemini_multi"


def test_gemini_missing_model_rejected():
	"""Gemini config missing 'model' is rejected."""
	config = {"language_code": "en-US"}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="gemini", config=config)


def test_gemini_missing_language_code_rejected():
	"""Gemini config missing 'language_code' is rejected."""
	config = {"model": "en-US-Studio-MultiSpeaker"}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="gemini", config=config)


# ============================================================================
# Edge TTS Config Validation
# ============================================================================

def test_edge_valid_config_accepted():
	"""Valid Edge TTS config is accepted."""
	c = TTSConfigurationCreate(name="Test", provider="edge", config=VALID_EDGE)
	assert c.config == VALID_EDGE


def test_edge_with_rate_and_volume_accepted():
	"""Edge TTS config with rate and volume is accepted."""
	config = {**VALID_EDGE, "rate": "+10%", "volume": "-5%"}
	c = TTSConfigurationCreate(name="Test", provider="edge", config=config)
	assert c.config["rate"] == "+10%"


def test_edge_missing_voice_1_rejected():
	"""Edge TTS config missing 'voice_1' is rejected."""
	config = {"voice_2": "en-US-GuyNeural"}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="edge", config=config)


def test_edge_missing_voice_2_rejected():
	"""Edge TTS config missing 'voice_2' is rejected."""
	config = {"voice_1": "en-US-AriaNeural"}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="edge", config=config)


def test_edge_invalid_rate_format_rejected():
	"""Edge TTS config with invalid rate format is rejected."""
	config = {**VALID_EDGE, "rate": "fast"}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="edge", config=config)


def test_edge_invalid_volume_format_rejected():
	"""Edge TTS config with invalid volume format is rejected."""
	config = {**VALID_EDGE, "volume": "100"}
	with pytest.raises(ValidationError):
		TTSConfigurationCreate(name="Test", provider="edge", config=config)


def test_edge_rate_zero_accepted():
	"""Edge TTS config with '+0%' rate is accepted."""
	config = {**VALID_EDGE, "rate": "+0%"}
	c = TTSConfigurationCreate(name="Test", provider="edge", config=config)
	assert c.config["rate"] == "+0%"


# ============================================================================
# TTSConfigurationUpdate Validation
# ============================================================================

def test_update_all_fields_optional():
	"""Update schema accepts empty body (all fields optional)."""
	u = TTSConfigurationUpdate()
	assert u.name is None
	assert u.provider is None
	assert u.config is None
	assert u.is_default is None


def test_update_partial_name_only():
	"""Update with only name is accepted."""
	u = TTSConfigurationUpdate(name="New Name")
	assert u.name == "New Name"
	assert u.provider is None


def test_update_invalid_provider_rejected():
	"""Update with invalid provider is rejected."""
	with pytest.raises(ValidationError):
		TTSConfigurationUpdate(provider="bad_provider")


def test_update_valid_provider_accepted():
	"""Update with valid provider is accepted."""
	u = TTSConfigurationUpdate(provider="openai")
	assert u.provider == "openai"


def test_update_provider_and_config_validated_together():
	"""When both provider and config are set, config is validated for that provider."""
	with pytest.raises(ValidationError):
		TTSConfigurationUpdate(
			provider="openai",
			config={"model": "tts-1-hd"}  # missing voice_1 and voice_2
		)


def test_update_config_without_provider_not_validated():
	"""Config without provider is NOT cross-validated (partial update)."""
	# Only config provided, no provider - no cross-validation applied
	u = TTSConfigurationUpdate(config={"anything": "goes"})
	assert u.config == {"anything": "goes"}
