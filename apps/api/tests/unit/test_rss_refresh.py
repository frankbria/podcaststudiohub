"""
Unit tests for the post-completion RSS feed refresh helper (issue #382).

refresh_project_rss_feed() bridges Celery's sync world into the async
RSSGenerationService. It must regenerate the feed only when one already
exists, and must never raise — a feed refresh failure must not fail the
episode-completion path that invokes it.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from src.tasks.rss_refresh import refresh_project_rss_feed


def _mock_async_session():
    """Return (ctx, session) mimicking AsyncSessionLocal() as an async CM."""
    session = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, session


def _mock_service(feed):
    """Return an RSSGenerationService mock whose get_rss_feed returns *feed*."""
    service = MagicMock()
    service.get_rss_feed = AsyncMock(return_value=feed)
    service.generate_rss_for_project = AsyncMock(return_value=feed)
    return service


class TestRefreshProjectRssFeed:
    def test_regenerates_when_feed_exists(self):
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()
        ctx, session = _mock_async_session()
        service = _mock_service(feed=MagicMock())

        with (
            patch("src.tasks.rss_refresh.celery_async_session", return_value=ctx),
            patch("src.tasks.rss_refresh.RSSGenerationService", return_value=service),
        ):
            assert refresh_project_rss_feed(project_id, user_id) is True

        service.get_rss_feed.assert_awaited_once_with(session, project_id)
        service.generate_rss_for_project.assert_awaited_once_with(
            session, project_id, user_id
        )

    def test_skips_when_no_feed_row(self):
        """No RSSFeed row means no platform consumes the feed yet — do nothing."""
        ctx, _session = _mock_async_session()
        service = _mock_service(feed=None)

        with (
            patch("src.tasks.rss_refresh.celery_async_session", return_value=ctx),
            patch("src.tasks.rss_refresh.RSSGenerationService", return_value=service),
        ):
            assert refresh_project_rss_feed(uuid.uuid4(), uuid.uuid4()) is False

        service.generate_rss_for_project.assert_not_awaited()

    def test_swallows_service_errors(self):
        """A ValueError (e.g. incomplete podcast_metadata) must not propagate."""
        ctx, _session = _mock_async_session()
        service = _mock_service(feed=MagicMock())
        service.generate_rss_for_project = AsyncMock(
            side_effect=ValueError("Missing metadata")
        )

        with (
            patch("src.tasks.rss_refresh.celery_async_session", return_value=ctx),
            patch("src.tasks.rss_refresh.RSSGenerationService", return_value=service),
        ):
            assert refresh_project_rss_feed(uuid.uuid4(), uuid.uuid4()) is False

    def test_swallows_session_errors(self):
        """Even a broken DB session must not raise out of the helper."""
        with patch(
            "src.tasks.rss_refresh.celery_async_session",
            side_effect=RuntimeError("pool gone"),
        ):
            assert refresh_project_rss_feed(uuid.uuid4(), uuid.uuid4()) is False

    def test_accepts_string_ids(self):
        """Celery callbacks hold string UUIDs; the helper normalizes them."""
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()
        ctx, session = _mock_async_session()
        service = _mock_service(feed=MagicMock())

        with (
            patch("src.tasks.rss_refresh.celery_async_session", return_value=ctx),
            patch("src.tasks.rss_refresh.RSSGenerationService", return_value=service),
        ):
            assert refresh_project_rss_feed(str(project_id), str(user_id)) is True

        service.get_rss_feed.assert_awaited_once_with(session, project_id)
