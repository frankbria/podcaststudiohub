"""Celery tasks read the database as a role that bypasses RLS (#649).

On the dev box the worker connected as the RLS-forced app role (no tenant
context in a task), so every Celery read returned nothing: 11 content
extractions reported their own existing rows "not found". CI never saw it
because it runs Celery code as the superuser. These tests run the Celery
session factories under each real role.
"""
import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url

import src.database as database
from src.config import settings
from src.models.project import Project
from src.models.user import User


def _as_role(user: str, password: str) -> str:
    """The configured database, reached as another role (host and port follow the environment)."""
    return make_url(settings.DATABASE_URL).set(username=user, password=password).render_as_string(hide_password=False)


# Migration 003's and 020's local/CI fallback passwords.
APP_ROLE_URL = _as_role("podcastfy_app", "podcastfy_app_password")
WORKER_ROLE_URL = _as_role("podcastfy_worker", "podcastfy_worker_password")


@pytest.fixture
def committed_project():
    """A tenant's project, committed as the superuser (visible to every role)."""
    tenant = uuid.uuid4()
    with database.SyncSessionLocal() as db:
        user = User(email=f"role649-{uuid.uuid4()}@test.local", password_hash="x", tenant_id=tenant)
        db.add(user)
        db.flush()
        project = Project(user_id=user.id, tenant_id=tenant, name="P")
        db.add(project)
        db.commit()
        user_id, project_id = user.id, project.id
    yield project_id
    with database.SyncSessionLocal() as db:
        db.delete(db.get(User, user_id))
        db.commit()


@pytest.fixture
def celery_url(monkeypatch):
    """Point the Celery session factories at a given role, with fresh engines."""

    def use(url):
        monkeypatch.setattr(settings, "CELERY_DATABASE_URL", url)
        monkeypatch.setattr(database, "_sync_engine", None)
        monkeypatch.setattr(database, "_sync_session_factory", None)

    yield use
    # monkeypatch restores the module globals; drop any engine built under a test URL.
    if database._sync_engine is not None:
        database._sync_engine.dispose()


def _sync_sees(project_id) -> bool:
    with database.SyncSessionLocal() as db:
        return db.get(Project, project_id) is not None


def _async_sees(project_id) -> bool:
    async def read():
        async with database.celery_async_session() as db:
            return (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()

    return asyncio.run(read()) is not None


def test_the_app_role_is_blind_inside_a_celery_task(committed_project, celery_url):
    """The failure #649 found on the dev box, reproduced: no tenant context, so FORCE RLS hides every row."""
    celery_url(APP_ROLE_URL)

    assert not _sync_sees(committed_project)
    assert not _async_sees(committed_project)


def test_the_worker_role_sees_rows_without_tenant_context(committed_project, celery_url):
    celery_url(WORKER_ROLE_URL)

    assert _sync_sees(committed_project)
    assert _async_sees(committed_project)


def test_without_a_celery_url_the_factories_fall_back_to_database_url(monkeypatch):
    monkeypatch.setattr(settings, "CELERY_DATABASE_URL", None)

    assert settings.celery_database_url == settings.DATABASE_URL
