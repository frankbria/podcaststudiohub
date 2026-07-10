"""
Celery tasks for podcast platform distribution
"""
import copy
from celery import Task
from datetime import datetime, timezone
from typing import Dict, Any
import logging

from src.worker import celery_app
from src.database import SyncSessionLocal
from src.config import settings
from src.utils.encryption import decrypt_credential_sync, is_sensitive_header
from src.tasks.retry_utils import calculate_backoff, should_retry_exception

logger = logging.getLogger(__name__)


def _decrypt_platform_config(config: Dict[str, Any], platform: str) -> Dict[str, Any]:
    """
    Decrypt encrypted credentials in a platform config dict.

    Uses a synchronous DB session since Celery tasks run outside async context.
    Only decrypts fields known to be encrypted by the distribution target service.

    Args:
        config: Platform config dict (may contain encrypted values)
        platform: Platform type for determining which fields to decrypt

    Returns:
        Config dict with credentials decrypted
    """
    decrypted = copy.deepcopy(config)
    session = SyncSessionLocal()
    try:
        if platform == "spotify":
            oauth = decrypted.get("oauth_tokens", {})
            if oauth.get("access_token"):
                oauth["access_token"] = decrypt_credential_sync(session, oauth["access_token"])
            if oauth.get("refresh_token"):
                oauth["refresh_token"] = decrypt_credential_sync(session, oauth["refresh_token"])
            decrypted["oauth_tokens"] = oauth

        elif platform == "apple_podcasts":
            creds = decrypted.get("credentials", {})
            if creds.get("api_key"):
                creds["api_key"] = decrypt_credential_sync(session, creds["api_key"])
            decrypted["credentials"] = creds

        elif platform == "webhook":
            headers = decrypted.get("headers", {})
            for key, value in headers.items():
                if is_sensitive_header(key) and value:
                    headers[key] = decrypt_credential_sync(session, value)
            decrypted["headers"] = headers

    finally:
        session.close()

    return decrypted


def _idempotency_key(episode_id: str, platform: str) -> str:
    """
    Canonical idempotency token for one episode/platform publish (issue #312).

    Stable across Celery redeliveries (acks_late + retries), so the platform
    API or webhook receiver can deduplicate a repeated publish.
    """
    return f"{episode_id}:{platform}"


def _merge_episode_metadata(episode: Any, passed_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build distribution metadata from an Episode row, overlaying any passed-in values.

    The workflow builder passes an empty ``episode_metadata`` because the audio's
    ``s3_url`` is only set by the upload stage that runs *before* distribution in
    the chain (issue #211). This reads the fresh Episode so Spotify/Apple/webhook
    receive a real title, description and audio URL instead of blanks.

    Args:
        episode: Episode ORM row (or any object exposing the same attributes).
        passed_metadata: Metadata forwarded by the caller; takes precedence over
            DB-sourced values for any key it provides (with a non-None value).

    Returns:
        Merged metadata dict. DB-sourced keys with a ``None`` value are omitted so
        downstream services fall back to their own defaults.
    """
    episode_meta = getattr(episode, "episode_metadata", None) or {}
    duration = getattr(episode, "duration_seconds", None)
    base: Dict[str, Any] = {
        "title": episode_meta.get("title"),
        "description": episode_meta.get("description"),
        "duration_seconds": float(duration) if duration is not None else None,
        "audio_url": getattr(episode, "s3_url", None),
        "explicit": episode_meta.get("explicit", False),
        "publish_date": episode_meta.get("publication_date"),
    }
    merged = {key: value for key, value in base.items() if value is not None}
    for key, value in (passed_metadata or {}).items():
        if value is not None:
            merged[key] = value
    return merged


@celery_app.task(bind=True, name="distribute_to_platform", time_limit=300, max_retries=5)
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

        # Populate episode metadata from the DB. The workflow builder passes an
        # empty dict because the audio (and its Episode.s3_url) is only available
        # after the upload stage that runs before this task; loading the Episode
        # here yields non-empty title/description/audio_url (issue #211). Any
        # passed-in values win.
        from src.models.episode import Episode
        from uuid import UUID as _UUID
        prior_result = None
        with SyncSessionLocal() as db:
            # Row lock so the completion check below observes committed state and
            # cannot race a concurrent callback's read-modify-write (issue #312).
            episode = db.get(Episode, _UUID(episode_id), with_for_update=True)
            if episode is not None:
                progress = getattr(episode, "generation_progress", None) or {}
                entry = (progress.get("distribution") or {}).get(platform) or {}
                if entry.get("status") == "complete":
                    # Redelivery after a recorded success — do not republish.
                    prior_result = {
                        "status": "success",
                        "platform": platform,
                        "platform_episode_id": entry.get("platform_episode_id"),
                        "platform_url": entry.get("platform_url"),
                        "error": None,
                    }
                else:
                    episode_metadata = _merge_episode_metadata(episode, episode_metadata)
            else:
                logger.warning(
                    "Episode %s not found while building distribution metadata",
                    episode_id,
                )

        if prior_result is not None:
            logger.info(
                "Episode %s already distributed to %s; skipping republish on redelivery.",
                episode_id,
                platform,
            )
            return prior_result

        # Never publish an episode whose audio was not actually uploaded. s3_url is
        # written by on_upload_complete only on a successful upload, so its absence
        # means the upload either failed or has not committed yet. Raising a
        # transient error lets the retry handler below wait (the success callback
        # races this chain task); after the retry budget is exhausted the task fails
        # without publishing rather than pushing a non-existent audio URL to the
        # platform (issue #211).
        if not episode_metadata.get("audio_url"):
            logger.warning(
                "Episode %s audio not available yet (no s3_url) for %s distribution; "
                "retrying before giving up.",
                episode_id, platform,
            )
            raise RuntimeError(
                f"Episode {episode_id} has no uploaded audio URL yet; cannot distribute."
            )

        # Decrypt any encrypted credentials in the config
        try:
            platform_config = _decrypt_platform_config(platform_config, platform)
        except Exception as e:
            logger.error(f"Failed to decrypt credentials for {platform}: {e}")
            return {
                "status": "failed",
                "platform": platform,
                "platform_episode_id": None,
                "platform_url": None,
                "error": f"Credential decryption failed: {type(e).__name__}"
            }

        if platform == "spotify":
            result = _distribute_to_spotify(episode_id, platform_config, episode_metadata, self)
        elif platform == "apple_podcasts":
            result = _distribute_to_apple(episode_id, platform_config, episode_metadata, self)
        elif platform == "webhook":
            result = _distribute_via_webhook(episode_id, platform_config, episode_metadata, self)
        else:
            raise ValueError(f"Unsupported platform: {platform}")

        # Record success durably before returning so a redelivery after this
        # point hits the pre-check above instead of republishing (issue #312).
        # The on_distribution_complete link callback re-merges the same entry
        # as idempotent redundancy. A recording failure must NOT raise:
        # retrying the task would repeat the platform side effect that just
        # succeeded. If recording fails AND the worker dies before ack, the
        # pre-check cannot catch the redelivery — the Idempotency-Key sent
        # with the publish is the remaining (receiver-side) dedup layer.
        if result.get("status") == "success":
            try:
                from src.tasks.callbacks import record_platform_distribution
                record_platform_distribution(episode_id, platform, result)
            except Exception as exc:
                logger.error(
                    "Failed to record %s distribution success for episode %s "
                    "in-task (callback will retry the record): %s",
                    platform,
                    episode_id,
                    exc,
                    exc_info=True,
                )

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
        if not should_retry_exception(e):
            # Permanent error (validation, unsupported platform, etc.) — don't retry
            logger.error(
                f"Permanent error distributing to {platform} for episode {episode_id}: {e}"
            )
            return {
                "status": "failed",
                "platform": platform,
                "platform_episode_id": None,
                "platform_url": None,
                "error": str(e)
            }
        # Transient error — retry with exponential backoff
        logger.warning(
            f"Transient error distributing to {platform} for episode {episode_id}, "
            f"attempt {self.request.retries + 1}/{self.max_retries + 1}: {e}"
        )
        try:
            raise self.retry(exc=e, countdown=calculate_backoff(self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error(
                f"Distribution to {platform} failed after {self.max_retries} retries "
                f"for episode {episode_id}: {e}"
            )
            return {
                "status": "failed",
                "platform": platform,
                "platform_episode_id": None,
                "platform_url": None,
                "error": str(e)
            }


def _distribute_to_spotify(episode_id: str, config: Dict, metadata: Dict, task: Task) -> Dict:
    """Distribute to Spotify for Podcasters using the Spotify Web API."""
    from src.services.spotify_service import SpotifyService

    task.update_state(
        state='PROGRESS',
        meta={
            'episode_id': episode_id,
            'platform': 'spotify',
            'progress': 25,
            'status': 'Authenticating with Spotify...'
        }
    )

    show_id = config.get("show_id")
    if not show_id:
        raise ValueError("Spotify show_id not configured for this distribution target")

    oauth_tokens = config.get("oauth_tokens", {})
    access_token = oauth_tokens.get("access_token")
    if not access_token:
        raise ValueError("No Spotify access token found. Please re-authorize the distribution target.")

    service = SpotifyService()

    # Refresh the access token if it is expired
    refresh_token = oauth_tokens.get("refresh_token")
    expires_at_str = oauth_tokens.get("expires_at")
    if expires_at_str and refresh_token:
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) >= expires_at:
                logger.info(
                    "Spotify access token expired for episode %s, refreshing...",
                    episode_id,
                )
                if not settings.SPOTIFY_CLIENT_ID or not settings.SPOTIFY_CLIENT_SECRET:  # type: ignore[truthy-bool]
                    raise ValueError(
                        "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set "
                        "to refresh Spotify OAuth tokens automatically."
                    )
                token_data = service.refresh_access_token(
                    refresh_token=refresh_token,
                    client_id=settings.SPOTIFY_CLIENT_ID,
                    client_secret=settings.SPOTIFY_CLIENT_SECRET,
                )
                access_token = token_data["access_token"]
                logger.info(
                    "Spotify access token refreshed for episode %s", episode_id
                )
        except (ValueError, KeyError, TypeError):
            # Re-raise permanent errors so the task does not retry
            raise
        except Exception as exc:
            # Log and continue with the existing token; let the API call
            # surface the actual auth error if the token is truly invalid.
            logger.warning(
                "Could not refresh Spotify token for episode %s: %s",
                episode_id,
                exc,
            )

    task.update_state(
        state='PROGRESS',
        meta={
            'episode_id': episode_id,
            'platform': 'spotify',
            'progress': 50,
            'status': 'Publishing episode to Spotify...'
        }
    )

    result = service.publish_episode(
        show_id=show_id,
        access_token=access_token,
        metadata=metadata,
        idempotency_key=_idempotency_key(episode_id, "spotify"),
    )

    logger.info(
        "Spotify distribution complete for episode %s: platform_id=%s",
        episode_id,
        result["episode_id"],
    )
    return {
        "status": "success",
        "platform": "spotify",
        "platform_episode_id": result["episode_id"],
        "platform_url": result["platform_url"],
        "error": None,
    }


def _distribute_to_apple(episode_id: str, config: Dict, metadata: Dict, task: Task) -> Dict:
    """Distribute to Apple Podcasts Connect using the Apple Podcasts Connect API."""
    from src.services.apple_podcasts_service import ApplePodcastsService

    task.update_state(
        state='PROGRESS',
        meta={
            'episode_id': episode_id,
            'platform': 'apple_podcasts',
            'progress': 25,
            'status': 'Authenticating with Apple Podcasts...'
        }
    )

    show_id = config.get("show_id")
    if not show_id:
        raise ValueError("Apple Podcasts show_id not configured for this distribution target")

    credentials = config.get("credentials", {})
    api_key = credentials.get("api_key")
    if not api_key:
        raise ValueError(
            "No Apple Podcasts API key found. Please re-add your credentials."
        )

    task.update_state(
        state='PROGRESS',
        meta={
            'episode_id': episode_id,
            'platform': 'apple_podcasts',
            'progress': 50,
            'status': 'Publishing episode to Apple Podcasts...'
        }
    )

    service = ApplePodcastsService()
    result = service.publish_episode(
        show_id=show_id,
        api_key=api_key,
        metadata=metadata,
        idempotency_key=_idempotency_key(episode_id, "apple_podcasts"),
    )

    logger.info(
        "Apple Podcasts distribution complete for episode %s: platform_id=%s",
        episode_id,
        result["episode_id"],
    )
    return {
        "status": "success",
        "platform": "apple_podcasts",
        "platform_episode_id": result["episode_id"],
        "platform_url": result["platform_url"],
        "error": None,
    }


def _distribute_via_webhook(episode_id: str, config: Dict, metadata: Dict, task: Task) -> Dict:
    """Distribute via webhook (n8n, Zapier, etc.)"""
    task.update_state(
        state='PROGRESS',
        meta={
            'episode_id': episode_id,
            'platform': 'webhook',
            'progress': 50,
            'status': 'Sending webhook...'
        }
    )

    webhook_url = config.get('url') or config.get('webhook_url')
    if not webhook_url:
        raise ValueError("Webhook URL not provided in config")

    # SSRF guard (issue #206): re-validate at dispatch time to defeat DNS
    # rebinding since the target was created/validated. Reject internal hosts
    # and non-standard ports; redirects are disabled below so a public host
    # cannot bounce the request into an internal address.
    from ..utils.pinned_fetch import pinned_session
    from ..utils.ssrf import SSRFValidationError, validate_public_url
    try:
        resolved = validate_public_url(
            webhook_url,
            allowed_schemes=("https",),
            allowed_ports={443},
            block_on_resolution_failure=True,
        )
    except SSRFValidationError as exc:
        raise ValueError(f"Webhook URL is not allowed: {exc}") from exc

    idempotency_key = _idempotency_key(episode_id, "webhook")
    headers = dict(config.get('headers', {}))
    headers["Idempotency-Key"] = idempotency_key
    method = config.get('method', 'POST')

    payload = {
        "episode_id": episode_id,
        "metadata": metadata,
        "event": "episode_published",
        "idempotency_key": idempotency_key,
    }

    # Send webhook with episode data (redirects disabled to prevent SSRF bounce).
    # Pin the connection to the validated IP so the client cannot re-resolve the
    # host to an internal address between validation and connect (#234).
    with pinned_session(webhook_url, resolved[0]) as session:
        if method == "POST":
            response = session.post(
                webhook_url, json=payload, headers=headers, timeout=30, allow_redirects=False
            )
        else:
            response = session.get(
                webhook_url, headers=headers, params=payload, timeout=30, allow_redirects=False
            )

    response.raise_for_status()

    return {
        "status": "success",
        "platform": "webhook",
        "platform_episode_id": None,
        "platform_url": webhook_url,
        "error": None
    }
