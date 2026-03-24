"""
Unit tests for PodcastService.

Tests cover:
- get_supported_tts_providers: returns expected list
- get_conversation_styles: returns expected list
- generate_podcast: delegates to cli_generate_podcast with correct args,
  uses tempdir when output_dir omitted, passes output_dir when provided
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


from src.services.podcast_service import PodcastService


@pytest.fixture
def service():
	return PodcastService()


# ===========================================================================
# get_supported_tts_providers
# ===========================================================================


@pytest.mark.asyncio
async def test_get_supported_tts_providers_returns_list(service):
	providers = await service.get_supported_tts_providers()
	assert isinstance(providers, list)
	assert len(providers) > 0


@pytest.mark.asyncio
async def test_get_supported_tts_providers_includes_openai(service):
	providers = await service.get_supported_tts_providers()
	assert "openai" in providers


@pytest.mark.asyncio
async def test_get_supported_tts_providers_includes_elevenlabs(service):
	providers = await service.get_supported_tts_providers()
	assert "elevenlabs" in providers


# ===========================================================================
# get_conversation_styles
# ===========================================================================


@pytest.mark.asyncio
async def test_get_conversation_styles_returns_list(service):
	styles = await service.get_conversation_styles()
	assert isinstance(styles, list)
	assert len(styles) > 0


@pytest.mark.asyncio
async def test_get_conversation_styles_includes_casual(service):
	styles = await service.get_conversation_styles()
	assert "casual" in styles


# ===========================================================================
# generate_podcast
# ===========================================================================


@pytest.mark.asyncio
async def test_generate_podcast_delegates_to_cli(service):
	"""generate_podcast should call cli_generate_podcast and return its result."""
	with patch("src.services.podcast_service.cli_generate_podcast", return_value="/tmp/out.mp3") as mock_cli:
		result = await service.generate_podcast(
			urls=["https://example.com"],
			tts_model="openai",
		)
	assert result == "/tmp/out.mp3"
	mock_cli.assert_called_once()


@pytest.mark.asyncio
async def test_generate_podcast_passes_output_dir(service):
	"""When output_dir is specified it should be forwarded to the CLI."""
	with patch("src.services.podcast_service.cli_generate_podcast", return_value="/custom/out.mp3") as mock_cli:
		await service.generate_podcast(
			urls=["https://example.com"],
			output_dir="/custom",
		)
	_, kwargs = mock_cli.call_args
	assert kwargs.get("output_dir") == "/custom"


@pytest.mark.asyncio
async def test_generate_podcast_creates_tempdir_when_no_output_dir(service):
	"""When output_dir is omitted a temporary directory should be used."""
	with patch("src.services.podcast_service.cli_generate_podcast", return_value="/tmp/x/out.mp3") as mock_cli, \
	     patch("src.services.podcast_service.tempfile.mkdtemp", return_value="/tmp/auto") as mock_tmpdir:
		await service.generate_podcast(urls=["https://example.com"])
	mock_tmpdir.assert_called_once()
	_, kwargs = mock_cli.call_args
	assert kwargs.get("output_dir") == "/tmp/auto"
