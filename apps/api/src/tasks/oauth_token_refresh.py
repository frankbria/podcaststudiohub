"""
Celery task for automatic OAuth token refresh.

Periodically checks all active Spotify distribution targets and refreshes
access tokens that are expiring within 24 hours.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

import httpx
from celery import Task

from src.worker import celery_app

logger = logging.getLogger(__name__)

# Refresh tokens that expire within this window
REFRESH_WINDOW_HOURS = 24


@celery_app.task(bind=True, name="refresh_oauth_tokens", time_limit=300)
def refresh_oauth_tokens_task(self: Task) -> Dict[str, Any]:
	"""
	Refresh expiring Spotify OAuth access tokens for all active distribution targets.

	Runs every 6 hours via Celery Beat. For each active Spotify distribution target
	whose access token expires within 24 hours, exchanges the stored refresh token
	for a new access token and updates the database record.

	Handles failures per-target gracefully: a failed refresh logs an error and
	deactivates the target (refresh_token invalid), but does not abort processing
	of other targets.

	Returns:
		Dict with summary: total checked, refreshed, failed, skipped counts.
	"""
	import asyncio

	result = asyncio.run(_refresh_oauth_tokens_async(self))
	return result


async def _refresh_oauth_tokens_async(task: Task) -> Dict[str, Any]:
	"""
	Async implementation of the token refresh logic.

	Uses an independent database session (not the request-scoped session) to
	support background execution without an active HTTP request.
	"""
	from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
	from sqlalchemy.orm import sessionmaker
	from sqlalchemy import select
	from sqlalchemy.pool import NullPool

	from src.config import settings
	from src.models.distribution_target import DistributionTarget
	from src.utils.encryption import decrypt_credential, encrypt_credential

	total_checked = 0
	total_refreshed = 0
	total_failed = 0
	total_skipped = 0

	engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
	async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

	try:
		async with async_session() as db:
			# Query all active Spotify targets
			result = await db.execute(
				select(DistributionTarget).where(
					DistributionTarget.target_type == "spotify",
					DistributionTarget.is_active.is_(True),
				)
			)
			targets = result.scalars().all()
			total_checked = len(targets)

			logger.info("Token refresh task: checking %d active Spotify targets", total_checked)

			now = datetime.now(timezone.utc)
			refresh_threshold = now + timedelta(hours=REFRESH_WINDOW_HOURS)

			for target in targets:
				config = target.config or {}
				oauth_tokens = config.get("oauth_tokens", {})
				expires_str = oauth_tokens.get("expires_at")
				encrypted_refresh = oauth_tokens.get("refresh_token")

				if not expires_str or not encrypted_refresh:
					logger.warning(
						"Target %s missing expires_at or refresh_token; skipping", target.id
					)
					total_skipped += 1
					continue

				# Parse expiry timestamp
				try:
					expires_at = datetime.fromisoformat(
						expires_str.replace("Z", "+00:00")
					)
				except (ValueError, TypeError):
					logger.warning(
						"Target %s has invalid expires_at '%s'; skipping", target.id, expires_str
					)
					total_skipped += 1
					continue

				# Only refresh if expiring within the window
				if expires_at > refresh_threshold:
					total_skipped += 1
					continue

				# Attempt token refresh
				try:
					refresh_token = await decrypt_credential(db, encrypted_refresh)
					new_tokens = await _call_spotify_refresh(
						refresh_token=refresh_token,
						client_id=settings.SPOTIFY_CLIENT_ID,
						client_secret=settings.SPOTIFY_CLIENT_SECRET,
					)

					new_access_token = new_tokens["access_token"]
					new_expires_in = new_tokens.get("expires_in", 3600)
					new_refresh_token = new_tokens.get("refresh_token")

					encrypted_access = await encrypt_credential(db, new_access_token)
					new_expires_at = (
						now + timedelta(seconds=new_expires_in)
					).isoformat()

					# Update refresh token if Spotify rotated it
					if new_refresh_token:
						encrypted_refresh = await encrypt_credential(db, new_refresh_token)

					updated_config = dict(config)
					updated_config["oauth_tokens"] = {
						**oauth_tokens,
						"access_token": encrypted_access,
						"refresh_token": encrypted_refresh,
						"expires_at": new_expires_at,
					}
					target.config = updated_config

					logger.info(
						"Token refresh task: refreshed target %s (expires %s)",
						target.id,
						new_expires_at,
					)
					total_refreshed += 1

				except Exception as exc:
					logger.error(
						"Token refresh task: failed to refresh target %s: %s",
						target.id,
						exc,
					)
					# Deactivate target if refresh_token is invalid (401 from Spotify)
					error_str = str(exc)
					if "401" in error_str or "invalid_grant" in error_str.lower():
						target.is_active = False
						logger.warning(
							"Token refresh task: deactivated target %s (invalid refresh_token)",
							target.id,
						)
					total_failed += 1

			# Commit all updates in a single transaction
			await db.commit()

	finally:
		await engine.dispose()

	summary = {
		"total_checked": total_checked,
		"total_refreshed": total_refreshed,
		"total_failed": total_failed,
		"total_skipped": total_skipped,
	}
	logger.info("Token refresh task complete: %s", summary)
	return summary


async def _call_spotify_refresh(
	refresh_token: str,
	client_id: str,
	client_secret: str,
) -> dict:
	"""
	Exchange a Spotify refresh token for a new access token.

	Args:
		refresh_token: Valid Spotify refresh token
		client_id: Spotify application client ID
		client_secret: Spotify application client secret

	Returns:
		Dict with access_token, expires_in, and optionally refresh_token

	Raises:
		httpx.HTTPStatusError: If the Spotify token endpoint returns an error
	"""
	async with httpx.AsyncClient() as client:
		response = await client.post(
			"https://accounts.spotify.com/api/token",
			data={
				"grant_type": "refresh_token",
				"refresh_token": refresh_token,
			},
			auth=(client_id, client_secret),
			headers={"Content-Type": "application/x-www-form-urlencoded"},
		)
		response.raise_for_status()
		return response.json()
