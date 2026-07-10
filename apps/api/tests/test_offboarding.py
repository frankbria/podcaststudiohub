"""
Tests for tenant offboarding / GDPR erasure (issue #308).

DELETE /auth/me permanently erases the authenticated user's account: every
Postgres row tied to the user (directly or via cascade), all S3 audio
objects, and local file artifacts.
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import select

from src.models.user import User
from src.models.billing_subscription import BillingSubscription
from src.models.billing_usage import BillingUsage
from src.models.project import Project
from src.models.episode import Episode
from src.models.episode_composition import EpisodeComposition
from src.models.audio_snippet import AudioSnippet
from src.models.rss_feed import RSSFeed
from src.models.content_source import ContentSource
from src.services.auth_service import verify_jwt_token


@pytest.fixture
async def seeded_user(client, test_db):
	"""Register a user and seed one of every kind of tenant-owned row that
	the offboarding routine must account for: a project, an episode (with
	s3_key + local file/transcript paths), an episode composition (with
	composed_s3_key + composed_file_path), an audio snippet (with s3_key), an
	RSS feed (with s3_key), a content source (with a JSONB s3_key), and
	billing subscription/usage rows (no FK to users).

	Returns a dict of everything a test needs to make assertions.
	"""
	reg_response = await client.post("/auth/register", json={
		"email": f"offboard_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "Offboard Me",
	})
	assert reg_response.status_code == 201
	token = reg_response.json()["access_token"]
	headers = {"Authorization": f"Bearer {token}"}
	claims = verify_jwt_token(token)
	user_id = claims["sub"]
	tenant_id = claims["tenant_id"]

	test_db.add(BillingSubscription(user_id=user_id, tenant_id=tenant_id, tier="enterprise"))
	test_db.add(BillingUsage(
		user_id=user_id,
		tenant_id=tenant_id,
		period_start=date(2026, 1, 1),
		period_end=date(2026, 1, 31),
	))
	await test_db.flush()

	proj_response = await client.post("/projects", headers=headers, json={
		"name": "Offboarding Project",
		"podcast_metadata": {
			"show_title": "Test Show",
			"author": "Test Author",
			"description": "Test Description",
		},
	})
	assert proj_response.status_code == 201
	project_id = proj_response.json()["id"]

	ep_response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Offboarding Episode", "description": "Desc"},
	})
	assert ep_response.status_code == 201
	episode_id = ep_response.json()["id"]

	from src.services.episode_service import get_episode_by_id, set_episode_system_fields
	from uuid import UUID as _UUID

	episode = await get_episode_by_id(test_db, _UUID(episode_id))
	await set_episode_system_fields(test_db, episode, s3_key="episodes/audio.mp3")

	test_db.add(EpisodeComposition(
		episode_id=episode_id,
		tenant_id=tenant_id,
		timeline=[],
		composed_s3_key="compositions/final.mp3",
	))
	test_db.add(AudioSnippet(
		user_id=user_id,
		project_id=project_id,
		tenant_id=tenant_id,
		name="Intro",
		snippet_type="intro",
		file_path="/tmp/intro.mp3",
		s3_key="snippets/intro.mp3",
	))
	test_db.add(RSSFeed(
		project_id=project_id,
		tenant_id=tenant_id,
		s3_key="feeds/project.xml",
	))
	test_db.add(ContentSource(
		episode_id=episode_id,
		tenant_id=tenant_id,
		source_type="pdf",
		source_data={"filename": "doc.pdf", "s3_key": "uploads/doc.pdf"},
		extraction_status="pending",
	))
	await test_db.flush()

	return {
		"headers": headers,
		"token": token,
		"user_id": user_id,
		"tenant_id": tenant_id,
		"project_id": project_id,
		"episode_id": episode_id,
		"s3_keys": {
			"episodes/audio.mp3",
			"compositions/final.mp3",
			"snippets/intro.mp3",
			"feeds/project.xml",
			"uploads/doc.pdf",
		},
	}


@pytest.mark.asyncio
async def test_delete_me_returns_204(seeded_user, client):
	"""DELETE /auth/me erases the account and returns 204."""
	with patch("src.services.offboarding_service.StorageService") as MockStorage:
		mock_instance = MockStorage.return_value
		mock_instance.delete_file = AsyncMock()
		response = await client.request(
			"DELETE", "/auth/me", headers=seeded_user["headers"],
			json={"password": "SecurePass123!"},
		)

	assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_me_deletes_one_s3_object_per_key(seeded_user, client):
	"""Every collected S3 key gets exactly one delete_file call."""
	with patch("src.services.offboarding_service.StorageService") as MockStorage:
		mock_instance = MockStorage.return_value
		mock_instance.delete_file = AsyncMock()
		response = await client.request(
			"DELETE", "/auth/me", headers=seeded_user["headers"],
			json={"password": "SecurePass123!"},
		)

	assert response.status_code == 204
	called_keys = {call.args[0] for call in mock_instance.delete_file.call_args_list}
	assert called_keys == seeded_user["s3_keys"]
	assert mock_instance.delete_file.call_count == len(seeded_user["s3_keys"])


@pytest.mark.asyncio
async def test_delete_me_removes_user_and_cascaded_rows(seeded_user, client, test_db):
	"""The user row and everything that cascades from it (project, episode,
	composition, audio snippet, RSS feed, content source) are gone."""
	with patch("src.services.offboarding_service.StorageService") as MockStorage:
		mock_instance = MockStorage.return_value
		mock_instance.delete_file = AsyncMock()
		response = await client.request(
			"DELETE", "/auth/me", headers=seeded_user["headers"],
			json={"password": "SecurePass123!"},
		)
	assert response.status_code == 204

	from uuid import UUID as _UUID

	user_result = await test_db.execute(
		select(User).where(User.id == _UUID(seeded_user["user_id"]))
	)
	assert user_result.scalar_one_or_none() is None

	project_result = await test_db.execute(
		select(Project).where(Project.id == _UUID(seeded_user["project_id"]))
	)
	assert project_result.scalar_one_or_none() is None

	episode_result = await test_db.execute(
		select(Episode).where(Episode.id == _UUID(seeded_user["episode_id"]))
	)
	assert episode_result.scalar_one_or_none() is None

	composition_result = await test_db.execute(
		select(EpisodeComposition).where(
			EpisodeComposition.episode_id == _UUID(seeded_user["episode_id"])
		)
	)
	assert composition_result.scalar_one_or_none() is None

	snippet_result = await test_db.execute(
		select(AudioSnippet).where(AudioSnippet.user_id == _UUID(seeded_user["user_id"]))
	)
	assert snippet_result.scalar_one_or_none() is None

	rss_result = await test_db.execute(
		select(RSSFeed).where(RSSFeed.project_id == _UUID(seeded_user["project_id"]))
	)
	assert rss_result.scalar_one_or_none() is None

	content_source_result = await test_db.execute(
		select(ContentSource).where(
			ContentSource.episode_id == _UUID(seeded_user["episode_id"])
		)
	)
	assert content_source_result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_me_removes_billing_rows(seeded_user, client, test_db):
	"""Billing rows are erased with the account. Their ORM models declare no FK,
	but migration 010 gave them user_id FKs with ON DELETE CASCADE, so the DB
	guarantees this outcome (mutation-testing the service can't break it)."""
	from uuid import UUID as _UUID

	# Guard against a vacuous test: the seeded rows must be visible up front.
	# (There may be more than one usage row — the metering middleware creates
	# them for every API call the fixture made.)
	pre_sub = await test_db.execute(
		select(BillingSubscription).where(
			BillingSubscription.user_id == _UUID(seeded_user["user_id"])
		)
	)
	assert pre_sub.scalars().all()
	pre_usage = await test_db.execute(
		select(BillingUsage).where(BillingUsage.user_id == _UUID(seeded_user["user_id"]))
	)
	assert pre_usage.scalars().all()

	with patch("src.services.offboarding_service.StorageService") as MockStorage:
		mock_instance = MockStorage.return_value
		mock_instance.delete_file = AsyncMock()
		response = await client.request(
			"DELETE", "/auth/me", headers=seeded_user["headers"],
			json={"password": "SecurePass123!"},
		)
	assert response.status_code == 204

	sub_result = await test_db.execute(
		select(BillingSubscription).where(
			BillingSubscription.user_id == _UUID(seeded_user["user_id"])
		)
	)
	assert sub_result.scalars().all() == []

	usage_result = await test_db.execute(
		select(BillingUsage).where(BillingUsage.user_id == _UUID(seeded_user["user_id"]))
	)
	assert usage_result.scalars().all() == []


@pytest.mark.asyncio
async def test_delete_me_invalidates_old_token(seeded_user, client):
	"""After erasure, the user's old bearer token is rejected."""
	with patch("src.services.offboarding_service.StorageService") as MockStorage:
		mock_instance = MockStorage.return_value
		mock_instance.delete_file = AsyncMock()
		response = await client.request(
			"DELETE", "/auth/me", headers=seeded_user["headers"],
			json={"password": "SecurePass123!"},
		)
	assert response.status_code == 204

	me_response = await client.get("/auth/me", headers=seeded_user["headers"])
	assert me_response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_delete_me_requires_auth(client):
	"""DELETE /auth/me without a token is rejected."""
	response = await client.request("DELETE", "/auth/me", json={"password": "SecurePass123!"})
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_me_wrong_password_rejected(seeded_user, client, test_db):
	"""A wrong password confirmation is a 403 and nothing is erased."""
	from uuid import UUID as _UUID

	with patch("src.services.offboarding_service.StorageService") as MockStorage:
		mock_instance = MockStorage.return_value
		mock_instance.delete_file = AsyncMock()
		response = await client.request(
			"DELETE", "/auth/me", headers=seeded_user["headers"],
			json={"password": "WrongPass456!"},
		)

	assert response.status_code == 403
	mock_instance.delete_file.assert_not_called()
	user_result = await test_db.execute(
		select(User).where(User.id == _UUID(seeded_user["user_id"]))
	)
	assert user_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_delete_me_refused_while_episode_generating(seeded_user, client, test_db):
	"""Erasure is refused (409) while an episode is mid-generation: the running
	Celery chain would re-upload audio after we deleted it (orphan class #308)."""
	from uuid import UUID as _UUID

	from src.services.episode_service import get_episode_by_id, set_episode_system_fields

	episode = await get_episode_by_id(test_db, _UUID(seeded_user["episode_id"]))
	await set_episode_system_fields(test_db, episode, generation_status="generating")

	with patch("src.services.offboarding_service.StorageService") as MockStorage:
		mock_instance = MockStorage.return_value
		mock_instance.delete_file = AsyncMock()
		response = await client.request(
			"DELETE", "/auth/me", headers=seeded_user["headers"],
			json={"password": "SecurePass123!"},
		)

	assert response.status_code == 409
	mock_instance.delete_file.assert_not_called()
	user_result = await test_db.execute(
		select(User).where(User.id == _UUID(seeded_user["user_id"]))
	)
	assert user_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_delete_me_s3_failure_does_not_block_erasure(seeded_user, client, test_db):
	"""S3 cleanup is best-effort: delete_file raising never blocks the erasure."""
	from uuid import UUID as _UUID

	with patch("src.services.offboarding_service.StorageService") as MockStorage:
		mock_instance = MockStorage.return_value
		mock_instance.delete_file = AsyncMock(side_effect=Exception("S3 unavailable"))
		response = await client.request(
			"DELETE", "/auth/me", headers=seeded_user["headers"],
			json={"password": "SecurePass123!"},
		)

	assert response.status_code == 204
	user_result = await test_db.execute(
		select(User).where(User.id == _UUID(seeded_user["user_id"]))
	)
	assert user_result.scalar_one_or_none() is None
