"""Hold state for episodes flagged by output screening (#576, #626).

One place reads it, so the distribution hold (generation task) and the audio
hold (upload task) cannot disagree about what "held" means.
"""
import re
import uuid
from typing import Optional

from src.database import SyncSessionLocal
from src.models.episode import Episode
from src.services.storage_service import CONTENT_REVIEW_METADATA

__all__ = ["CONTENT_REVIEW_METADATA", "episode_held_for_review", "held_episode_of"]

# build_podcast_s3_key's layout; only canonical episode audio can be held.
_EPISODE_AUDIO_KEY = re.compile(
    r"podcasts/user-[0-9a-f-]{36}/episode-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.mp3"
)


def episode_held_for_review(episode_id: str) -> bool:
    """True while screening flags on this episode await the user's review."""
    with SyncSessionLocal() as db:
        episode = db.get(Episode, uuid.UUID(episode_id))
        progress = (episode.generation_progress or {}) if episode is not None else {}
        return progress.get("content_review") == "pending"


def held_episode_of(s3_key: str) -> Optional[str]:
    """The episode id when ``s3_key`` is held episode audio, else None.

    Any key that is not canonical episode audio returns None without a DB read.
    """
    found = _EPISODE_AUDIO_KEY.fullmatch(s3_key)
    if found and episode_held_for_review(found.group(1)):
        return found.group(1)
    return None
