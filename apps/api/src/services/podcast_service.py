"""Podcast generation service wrapping existing podcastfy CLI"""

from typing import Optional, List, Dict, Any
from pathlib import Path
import tempfile

# Import existing podcastfy functionality
from podcastfy.client import generate_podcast as cli_generate_podcast


class PodcastService:
    """Service for podcast generation operations"""

    def __init__(self):
        pass

    async def generate_podcast(
        self,
        urls: Optional[List[str]] = None,
        file_paths: Optional[List[str]] = None,
        text_content: Optional[str] = None,
        tts_model: str = "openai",
        conversation_config: Optional[Dict[str, Any]] = None,
        longform: bool = False,
        output_dir: Optional[str] = None,
    ) -> str:
        """
        Generate podcast using existing podcastfy CLI

        Args:
            urls: List of URLs to extract content from
            file_paths: List of file paths (PDFs, etc.)
            text_content: Raw text content
            tts_model: TTS provider ('openai', 'elevenlabs', 'gemini', 'edge')
            conversation_config: Custom conversation configuration
            longform: Enable long-form podcast generation
            output_dir: Output directory for generated audio

        Returns:
            Path to generated audio file
        """
        # Use temporary directory if output_dir not specified
        if not output_dir:
            output_dir = tempfile.mkdtemp()

        # Call existing CLI function
        audio_file = cli_generate_podcast(
            urls=urls,
            file_paths=file_paths,
            text=text_content,
            tts_model=tts_model,
            conversation_config=conversation_config,
            longform=longform,
            output_dir=output_dir,
        )

        return audio_file

    async def get_supported_tts_providers(self) -> List[str]:
        """Get list of supported TTS providers"""
        return ["openai", "elevenlabs", "gemini", "geminimulti", "edge"]

    async def get_conversation_styles(self) -> List[str]:
        """Get list of available conversation styles"""
        return ["casual", "formal", "humorous", "educational", "debate"]
