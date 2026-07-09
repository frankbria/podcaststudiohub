"""Concurrency regression tests for usage metering (#296).

The shared ``test_db`` fixture isolates each test inside a single rolled-back
transaction, so it cannot model genuine parallel commits. These tests therefore
build their own engine and run each concurrent tracker in its *own* session /
connection (NullPool) so the upsert + atomic-increment paths face a real race
against the live test database. Committed rows are cleaned up at the end.
"""
import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from src.models.billing_usage import BillingUsage
from src.models.user import User
from src.services.usage_service import (
	_current_period_dates,
	track_api_call,
	track_episode_creation,
)

TEST_DATABASE_URL = os.environ.get(
	"TEST_DATABASE_URL",
	"postgresql+asyncpg://podcastfy_app:podcastfy_app_password@localhost:5432/podcastfy",
)

CONCURRENCY = 12


@pytest.fixture
async def committing_session_factory():
	"""Engine + session factory whose sessions commit for real (no rollback).

	Yields ``(factory, cleanup)``; ``cleanup`` removes any billing/user rows the
	test committed so the shared test DB stays clean.
	"""
	engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, echo=False)
	factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
	created_users: list = []  # (user_id, tenant_id) pairs

	async def cleanup():
		# billing_usage and users are both FORCE RLS (#304) — every delete
		# needs the owning tenant's context, so work per-user/per-transaction.
		async with factory() as session:
			for uid, tid in created_users:
				await session.execute(text(f"SET LOCAL app.tenant_id = '{tid}'"))
				await session.execute(
					delete(BillingUsage).where(BillingUsage.user_id == uid)
				)
				await session.execute(delete(User).where(User.id == uid))
				await session.commit()
		await engine.dispose()

	yield factory, created_users

	await cleanup()


async def _make_user(factory) -> tuple:
	"""Create and commit a real user; return (user_id, tenant_id)."""
	user_id = uuid4()
	tenant_id = uuid4()
	async with factory() as session:
		# INSERT must satisfy WITH CHECK (tenant_id = app.tenant_id) since #304.
		await session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
		session.add(
			User(
				id=user_id,
				email=f"concurrency_{user_id}@example.com",
				password_hash="x",
				tenant_id=tenant_id,
			)
		)
		await session.commit()
	return user_id, tenant_id


async def _count_rows(factory, user_id, tenant_id, period_start) -> int:
	async with factory() as session:
		await session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
		return (
			await session.execute(
				select(func.count())
				.select_from(BillingUsage)
				.where(
					BillingUsage.user_id == user_id,
					BillingUsage.period_start == period_start,
				)
			)
		).scalar_one()


async def _get_usage(factory, user_id, tenant_id, period_start) -> BillingUsage:
	async with factory() as session:
		await session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
		# scalar_one() raises MultipleResultsFound if duplicates leaked through.
		return (
			await session.execute(
				select(BillingUsage).where(
					BillingUsage.user_id == user_id,
					BillingUsage.period_start == period_start,
				)
			)
		).scalar_one()


@pytest.mark.asyncio
async def test_concurrent_episode_tracking_no_duplicates_or_lost_updates(
	committing_session_factory,
):
	factory, created_users = committing_session_factory
	user_id, tenant_id = await _make_user(factory)
	created_users.append((user_id, tenant_id))
	period_start, _ = _current_period_dates()

	async def track_once():
		# Independent session/connection per coroutine = genuine parallel commits.
		async with factory() as session:
			await session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
			await track_episode_creation(session, user_id, tenant_id)

	await asyncio.gather(*(track_once() for _ in range(CONCURRENCY)))

	assert await _count_rows(factory, user_id, tenant_id, period_start) == 1
	usage = await _get_usage(factory, user_id, tenant_id, period_start)
	assert usage.episodes_created == CONCURRENCY


@pytest.mark.asyncio
async def test_concurrent_api_call_tracking_no_duplicates_or_lost_updates(
	committing_session_factory,
):
	factory, created_users = committing_session_factory
	user_id, tenant_id = await _make_user(factory)
	created_users.append((user_id, tenant_id))
	period_start, _ = _current_period_dates()

	async def track_once():
		async with factory() as session:
			await session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
			await track_api_call(session, user_id, tenant_id)

	await asyncio.gather(*(track_once() for _ in range(CONCURRENCY)))

	assert await _count_rows(factory, user_id, tenant_id, period_start) == 1
	usage = await _get_usage(factory, user_id, tenant_id, period_start)
	assert usage.api_calls == CONCURRENCY
