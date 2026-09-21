"""In-repo podcast generation engine (epic #538).

Step 1 (#541) is the script layer: sources in, a validated ``Script`` out, with
prompts versioned in this repo and provider SDKs called directly. TTS is #542;
the live Celery task still calls podcastfy until #543 cuts it over.

Nothing under this package may import the dependency tree podcastfy pulled in —
that is the point of owning it. ``tests/test_dependency_reachability.py`` holds
the exact banned list and enforces it at both source and import-graph level.
"""
from src.engine.llm import EngineError, ProviderError, ScriptSchemaError
from src.engine.models import ConversationConfig, Script, Turn
from src.engine.script import ScriptValidationError, generate_script
from src.engine.transcript import build_transcript_s3_key, persist_transcript

__all__ = [
    "ConversationConfig",
    "EngineError",
    "ProviderError",
    "Script",
    "ScriptSchemaError",
    "ScriptValidationError",
    "Turn",
    "build_transcript_s3_key",
    "generate_script",
    "persist_transcript",
]
