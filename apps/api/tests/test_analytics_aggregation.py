"""
Characterization tests for analytics SQL aggregation (issue #274).

These pin the EXACT return-dict shapes of `get_episode_analytics` and
`get_project_analytics` so the in-memory loops can be replaced with SQL
aggregation without changing the frontend contract. They create a real
project/episode via the API (FK parents), seed a known set of AnalyticsEvent
rows directly on the session with custom dates/device/country/metadata, then
assert the full returned dict.
"""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest

from src.models.analytics_event import AnalyticsEvent
from src.services.analytics_service import (
    get_episode_analytics,
    get_project_analytics,
)


async def _setup_project_episode(client):
    """Register a user and create a project + episode; return (project_id, episode_id) as UUIDs."""
    resp = await client.post("/auth/register", json={
        "email": f"test_{uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "Test User",
    })
    assert resp.status_code == 201, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    resp = await client.post("/projects", json={
        "name": f"Test Project {uuid4()}",
        "description": "Analytics test project",
        "podcast_metadata": {
            "show_title": "Analytics Test Show",
            "author": "Test Author",
            "description": "Analytics test project",
        },
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    project_id = UUID(resp.json()["id"])

    resp = await client.post("/episodes", json={
        "project_id": str(project_id),
        "episode_metadata": {"title": f"Test Episode {uuid4()}", "description": "Test"},
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    episode_id = UUID(resp.json()["id"])

    return project_id, episode_id


def _mk_event(*, episode_id, project_id, event_type, created_at,
              device_type=None, app_name=None, country=None, metadata=None):
    return AnalyticsEvent(
        tenant_id=uuid4(),  # no FK / no RLS on analytics_events
        episode_id=episode_id,
        project_id=project_id,
        event_type=event_type,
        device_type=device_type,
        app_name=app_name,
        country=country,
        event_metadata=metadata,
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_get_episode_analytics_characterization(client, test_db):
    """Exact dict for a mixed set of events within an explicit date window."""
    proj, ep = await _setup_project_episode(client)
    date_from = datetime(2026, 6, 1)
    date_to = datetime(2026, 6, 30, 23, 59, 59)

    events = [
        _mk_event(episode_id=ep, project_id=proj, event_type="download",
                  created_at=datetime(2026, 6, 10), device_type="mobile",
                  app_name="apple_podcasts", country="US"),
        _mk_event(episode_id=ep, project_id=proj, event_type="download",
                  created_at=datetime(2026, 6, 11), device_type="desktop",
                  app_name="spotify", country="GB"),
        _mk_event(episode_id=ep, project_id=proj, event_type="play",
                  created_at=datetime(2026, 6, 12), device_type="mobile",
                  app_name="apple_podcasts", country="US",
                  metadata={"duration_listened_seconds": 120, "completed": True}),
        _mk_event(episode_id=ep, project_id=proj, event_type="play",
                  created_at=datetime(2026, 6, 13), device_type="tablet",
                  app_name="overcast", country="US",
                  metadata={"duration_listened_seconds": 60, "completed": False}),
        # play with empty metadata + NULL device/app/country: counted as play only
        _mk_event(episode_id=ep, project_id=proj, event_type="play",
                  created_at=datetime(2026, 6, 14), metadata={}),
        _mk_event(episode_id=ep, project_id=proj, event_type="stream",
                  created_at=datetime(2026, 6, 15), device_type="desktop",
                  app_name="other", country="GB"),
        _mk_event(episode_id=ep, project_id=proj, event_type="share",
                  created_at=datetime(2026, 6, 16), device_type="mobile",
                  app_name="other", country="US"),
        # outside the window -> excluded entirely
        _mk_event(episode_id=ep, project_id=proj, event_type="download",
                  created_at=datetime(2026, 7, 5), device_type="mobile",
                  app_name="apple_podcasts", country="US"),
    ]
    for e in events:
        test_db.add(e)
    await test_db.flush()

    result = await get_episode_analytics(test_db, ep, date_from=date_from, date_to=date_to)

    assert result == {
        "episode_id": ep,
        "period": {"from": date_from, "to": date_to},
        "metrics": {
            "total_downloads": 2,
            "total_plays": 3,
            "total_streams": 1,
            "average_listen_duration_seconds": 90.0,
            "completion_rate": 1 / 3,
        },
        "device_breakdown": {"mobile": 3, "desktop": 2, "tablet": 1, "unknown": 0},
        "app_breakdown": {"apple_podcasts": 2, "spotify": 1, "overcast": 1, "other": 2},
        "top_countries": [
            {"country": "US", "downloads": 4},
            {"country": "GB", "downloads": 2},
        ],
    }


@pytest.mark.asyncio
async def test_get_episode_analytics_zero_events(test_db):
    """No events -> zero metrics, no division error, empty breakdowns/countries."""
    ep = uuid4()
    date_from = datetime(2026, 6, 1)
    date_to = datetime(2026, 6, 30)

    result = await get_episode_analytics(test_db, ep, date_from=date_from, date_to=date_to)

    assert result == {
        "episode_id": ep,
        "period": {"from": date_from, "to": date_to},
        "metrics": {
            "total_downloads": 0,
            "total_plays": 0,
            "total_streams": 0,
            "average_listen_duration_seconds": 0.0,
            "completion_rate": 0.0,
        },
        "device_breakdown": {"mobile": 0, "desktop": 0, "tablet": 0, "unknown": 0},
        "app_breakdown": {},
        "top_countries": [],
    }


@pytest.mark.asyncio
async def test_get_project_analytics_characterization(client, test_db):
    """Exact dict for a project summary using now-relative dates (default 30d window)."""
    proj, ep = await _setup_project_episode(client)
    now = datetime.utcnow()

    in_window = [
        _mk_event(episode_id=ep, project_id=proj, event_type="download",
                  created_at=now - timedelta(days=2)),
        _mk_event(episode_id=ep, project_id=proj, event_type="download",
                  created_at=now - timedelta(days=3)),
        _mk_event(episode_id=ep, project_id=proj, event_type="play",
                  created_at=now - timedelta(days=4),
                  metadata={"duration_listened_seconds": 120, "completed": True}),
        _mk_event(episode_id=ep, project_id=proj, event_type="play",
                  created_at=now - timedelta(days=5),
                  metadata={"duration_listened_seconds": 60}),
        _mk_event(episode_id=ep, project_id=proj, event_type="play",
                  created_at=now - timedelta(days=6), metadata={}),
        _mk_event(episode_id=ep, project_id=proj, event_type="stream",
                  created_at=now - timedelta(days=7)),
        _mk_event(episode_id=ep, project_id=proj, event_type="share",
                  created_at=now - timedelta(days=8)),
    ]
    # outside the 30-day window -> excluded
    outside = _mk_event(episode_id=ep, project_id=proj, event_type="download",
                        created_at=now - timedelta(days=40))
    for e in in_window + [outside]:
        test_db.add(e)
    await test_db.flush()

    # Expected weekly buckets: same formula the service uses, applied to the
    # in-window event dates. This pins grouping/counts; the "%Y-W%W" format is
    # preserved by construction (the service still buckets in Python).
    weekly: dict[str, int] = {}
    for e in in_window:
        wk = e.created_at.strftime("%Y-W%W")
        weekly[wk] = weekly.get(wk, 0) + 1
    expected_weekly = [{"week": w, "downloads": c} for w, c in sorted(weekly.items())]

    result = await get_project_analytics(test_db, proj, days=30)

    assert result["project_id"] == proj
    assert result["period"]["days"] == 30
    assert result["summary"] == {
        "total_downloads": 2,
        "total_plays": 3,
        "total_listen_hours": 0.05,
    }
    assert result["trends"] == {"weekly_downloads": expected_weekly}
    assert result["top_episodes"] == [{"episode_id": str(ep), "downloads": 2}]


@pytest.mark.asyncio
async def test_get_project_analytics_zero_events(test_db):
    """No events -> zero summary, empty trends/top_episodes."""
    proj = uuid4()
    result = await get_project_analytics(test_db, proj, days=7)

    assert result["project_id"] == proj
    assert result["period"]["days"] == 7
    assert result["summary"] == {
        "total_downloads": 0,
        "total_plays": 0,
        "total_listen_hours": 0.0,
    }
    assert result["trends"] == {"weekly_downloads": []}
    assert result["top_episodes"] == []
