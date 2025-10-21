"""
Celery tasks for podcast platform distribution
"""
from celery import Task
from typing import Dict, Any
import logging

from src.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="distribute_to_platform", time_limit=300)
def distribute_to_platform_task(
    self: Task,
    episode_id: str,
    platform: str,
    platform_config: Dict[str, Any],
    episode_metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Distribute a podcast episode to a platform (Spotify, Apple Podcasts, etc.).

    Args:
        self: Celery task instance
        episode_id: UUID of the episode
        platform: Platform name (spotify, apple_podcasts, webhook)
        platform_config: Platform-specific configuration and credentials
        episode_metadata: Episode metadata for distribution

    Returns:
        Dictionary with distribution results
    """
    try:
        self.update_state(
            state='PROGRESS',
            meta={
                'episode_id': episode_id,
                'platform': platform,
                'progress': 0,
                'status': f'Starting distribution to {platform}...'
            }
        )

        if platform == "spotify":
            result = _distribute_to_spotify(episode_id, platform_config, episode_metadata, self)
        elif platform == "apple_podcasts":
            result = _distribute_to_apple(episode_id, platform_config, episode_metadata, self)
        elif platform == "webhook":
            result = _distribute_via_webhook(episode_id, platform_config, episode_metadata, self)
        else:
            raise ValueError(f"Unsupported platform: {platform}")

        self.update_state(
            state='SUCCESS',
            meta={
                'episode_id': episode_id,
                'platform': platform,
                'progress': 100,
                'status': 'Distribution successful'
            }
        )

        return result

    except Exception as e:
        logger.error(f"Distribution to {platform} failed for episode {episode_id}: {str(e)}")
        return {
            "status": "failed",
            "platform": platform,
            "platform_episode_id": None,
            "platform_url": None,
            "error": str(e)
        }


def _distribute_to_spotify(episode_id: str, config: Dict, metadata: Dict, task: Task) -> Dict:
    """Distribute to Spotify for Podcasters (placeholder)"""
    # Implementation would use Spotify's API
    # For now, return placeholder
    task.update_state(
        state='PROGRESS',
        meta={
            'episode_id': episode_id,
            'platform': 'spotify',
            'progress': 50,
            'status': 'Authenticating with Spotify...'
        }
    )
    # Spotify API integration would go here
    return {
        "status": "success",
        "platform": "spotify",
        "platform_episode_id": "spotify_placeholder_id",
        "platform_url": None,
        "error": None
    }


def _distribute_to_apple(episode_id: str, config: Dict, metadata: Dict, task: Task) -> Dict:
    """Distribute to Apple Podcasts Connect (placeholder)"""
    # Implementation would use Apple's Podcasts Connect API
    task.update_state(
        state='PROGRESS',
        meta={
            'episode_id': episode_id,
            'platform': 'apple_podcasts',
            'progress': 50,
            'status': 'Authenticating with Apple Podcasts...'
        }
    )
    # Apple API integration would go here
    return {
        "status": "success",
        "platform": "apple_podcasts",
        "platform_episode_id": "apple_placeholder_id",
        "platform_url": None,
        "error": None
    }


def _distribute_via_webhook(episode_id: str, config: Dict, metadata: Dict, task: Task) -> Dict:
    """Distribute via webhook (n8n, Zapier, etc.)"""
    import requests

    task.update_state(
        state='PROGRESS',
        meta={
            'episode_id': episode_id,
            'platform': 'webhook',
            'progress': 50,
            'status': 'Sending webhook...'
        }
    )

    webhook_url = config.get('webhook_url')
    if not webhook_url:
        raise ValueError("Webhook URL not provided in config")

    # Send webhook with episode data
    response = requests.post(
        webhook_url,
        json={
            "episode_id": episode_id,
            "metadata": metadata,
            "event": "episode_published"
        },
        timeout=30
    )

    response.raise_for_status()

    return {
        "status": "success",
        "platform": "webhook",
        "platform_episode_id": None,
        "platform_url": webhook_url,
        "error": None
    }
