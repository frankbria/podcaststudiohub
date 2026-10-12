"""_load_native_inputs against the real database (issue #543, PR A).

The native engine reads the stored TTS provider and the raw config from the
episode row, because the router sends podcastfy's renamed provider and nested
voice shape. Rows are committed through the sync ORM (the task's own session
cannot see the API test client's uncommitted transaction), and the user is
deleted afterwards; ON DELETE CASCADE removes the rest.
"""
import uuid

import pytest

from src.database import SyncSessionLocal
from src.engine import EngineError
from src.models.episode import Episode
from src.models.project import Project
from src.models.tts_configuration import TTSConfiguration
from src.models.user import User
from src.tasks.podcast_generation import _load_native_inputs

GEMINI_MULTI = {"model": "gemini-2.5-flash-tts", "language_code": "en-US"}
ELEVENLABS = {"model": "eleven_v3", "voice_1_id": "voiceA", "voice_2_id": "voiceB"}


@pytest.fixture
def make_episode():
    """Commit a user + project + episode, optionally with TTS configs."""
    created = []

    def make(episode_tts=None, project_tts=None):
        tenant_id = uuid.uuid4()
        with SyncSessionLocal() as db:
            user = User(
                email=f"native-inputs-{uuid.uuid4()}@test.local",
                password_hash="x",
                tenant_id=tenant_id,
            )
            db.add(user)
            db.flush()

            def tts(spec):
                if spec is None:
                    return None
                provider, config = spec
                row = TTSConfiguration(
                    user_id=user.id, tenant_id=tenant_id, name=provider,
                    provider=provider, config=config,
                )
                db.add(row)
                db.flush()
                return row.id

            project = Project(
                user_id=user.id, tenant_id=tenant_id, name="P",
                default_tts_config_id=tts(project_tts),
            )
            db.add(project)
            db.flush()
            episode = Episode(
                user_id=user.id, project_id=project.id, tenant_id=tenant_id,
                episode_number=1, episode_metadata={"title": "E"},
                tts_config_id=tts(episode_tts),
            )
            db.add(episode)
            db.commit()
            created.append(user.id)
            return str(episode.id), str(user.id)

    yield make
    with SyncSessionLocal() as db:
        for user_id in created:
            db.delete(db.get(User, user_id))
        db.commit()


def test_the_episode_config_is_read_with_its_stored_provider_name(make_episode):
    episode_id, user_id = make_episode(episode_tts=("gemini_multi", GEMINI_MULTI))

    assert _load_native_inputs(episode_id) == (user_id, "gemini_multi", GEMINI_MULTI)


def test_the_episode_config_wins_over_the_project_default(make_episode):
    episode_id, _ = make_episode(
        episode_tts=("gemini_multi", GEMINI_MULTI),
        project_tts=("elevenlabs", ELEVENLABS),
    )

    assert _load_native_inputs(episode_id)[1] == "gemini_multi"


def test_the_project_default_applies_when_the_episode_has_none(make_episode):
    episode_id, _ = make_episode(project_tts=("elevenlabs", ELEVENLABS))

    _, provider, config = _load_native_inputs(episode_id)

    assert (provider, config) == ("elevenlabs", ELEVENLABS)


def test_an_unconfigured_episode_gets_podcastfys_default_voices(make_episode):
    """Behaviour-preserving: podcastfy's own defaults were openai echo / shimmer."""
    episode_id, _ = make_episode()

    _, provider, config = _load_native_inputs(episode_id)

    assert provider == "openai"
    assert (config["voice_1"], config["voice_2"]) == ("echo", "shimmer")


def test_an_unknown_episode_is_refused():
    with pytest.raises(EngineError):
        _load_native_inputs(str(uuid.uuid4()))

