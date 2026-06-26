"""
Integration tests for the Celery podcast generation workflow [GAP-026].

Verifies that generate_podcast_task correctly chains downstream tasks:
  generation → S3 upload → [optional composition] → [optional distribution]

All database and external service interactions are mocked so no real
infrastructure is required.
"""
import uuid
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_episode(episode_id: str, user_id: str = None) -> MagicMock:
    """Return a MagicMock that behaves like an Episode ORM object."""
    ep = MagicMock()
    ep.id = uuid.UUID(episode_id)
    ep.user_id = uuid.UUID(user_id) if user_id else uuid.uuid4()
    ep.generation_status = "generating"
    ep.generation_progress = {}
    ep.file_path = None
    ep.s3_url = None
    ep.s3_key = None
    ep.duration_seconds = None
    ep.file_size_bytes = None
    ep.transcript_path = None
    ep.platform_ids = {}
    ep.error_message = None
    return ep


def _invoke_task(task, **kwargs):
    """
    Invoke a bind=True Celery task's run() method without a real broker.

    Sets a fake request ID and patches update_state so progress calls succeed.
    """
    task.request.update(id="test-" + str(uuid.uuid4()))
    with patch.object(task, "update_state", MagicMock()):
        return task.run(**kwargs)


def _mock_session_with_episode(user_id: str = "11111111-1111-1111-1111-111111111111") -> MagicMock:
    """Mock a SyncSessionLocal context manager yielding an episode with user_id.

    generate_podcast_task resolves episode.user_id for the tenant-scoped S3 key
    and fails closed when it cannot (issue #215), so workflow-dispatch tests must
    seed an episode rather than relying on the empty test DB.
    """
    episode = MagicMock()
    episode.user_id = user_id
    session = MagicMock()
    session.get.return_value = episode
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


def _make_generation_result(audio_file_path: str = "/tmp/episode.mp3") -> dict:
    return {
        "status": "success",
        "audio_file_path": audio_file_path,
        "transcript_path": audio_file_path.replace(".mp3", "_transcript.txt"),
        "duration_seconds": 300.0,
        "file_size_bytes": 5_000_000,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Test 1: Full workflow chain (generation → upload → composition → distribution)
# ---------------------------------------------------------------------------

class TestFullWorkflowChain:
    """Verify generate_podcast_task dispatches the full chain when all stages enabled."""

    def test_workflow_chain_dispatched_when_composition_enabled(self):
        """When enable_composition=True, build_generation_workflow is called."""
        import sys
        import types

        episode_id = str(uuid.uuid4())
        mock_audio_path = "/tmp/test_podcast.mp3"

        mock_audio_segment = MagicMock()
        mock_audio_segment.__len__ = MagicMock(return_value=60_000)

        mock_client = MagicMock()
        mock_podcastfy = types.ModuleType("podcastfy")
        mock_podcastfy.client = mock_client
        mock_client.generate_podcast = MagicMock(return_value=mock_audio_path)

        mock_chain = MagicMock()

        from src.tasks.podcast_generation import generate_podcast_task

        with (
            patch.dict(sys.modules, {"podcastfy": mock_podcastfy, "podcastfy.client": mock_client}),
            patch("src.tasks.podcast_generation.os.path.getsize", return_value=1000),
            patch("src.tasks.podcast_generation.AudioSegment") as mock_audio_cls,
            patch("src.tasks.podcast_generation.build_generation_workflow", return_value=mock_chain) as mock_builder,
            patch("src.tasks.podcast_generation.finalize_episode_generation_task"),
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=_mock_session_with_episode()),
        ):
            mock_audio_cls.from_file.return_value = mock_audio_segment

            result = _invoke_task(
                generate_podcast_task,
                episode_id=episode_id,
                urls=["https://example.com"],
                enable_composition=True,
                composition_timeline=[{"file_path": "/tmp/intro.mp3"}],
                enable_distribution=False,
            )

        assert result["status"] == "success"
        mock_builder.assert_called_once()
        call_kwargs = mock_builder.call_args.kwargs
        assert call_kwargs["episode_id"] == episode_id
        assert call_kwargs["audio_file_path"] == mock_audio_path
        assert call_kwargs["enable_composition"] is True
        assert call_kwargs["enable_distribution"] is False
        mock_chain.apply_async.assert_called_once()

    def test_workflow_chain_dispatched_when_distribution_enabled(self):
        """When enable_distribution=True with platforms, build_generation_workflow is called."""
        import sys
        import types

        episode_id = str(uuid.uuid4())
        mock_audio_path = "/tmp/dist_test.mp3"
        platforms = {"spotify": {"oauth_tokens": {}}, "webhook": {"url": "https://hook.example.com"}}

        mock_audio_segment = MagicMock()
        mock_audio_segment.__len__ = MagicMock(return_value=120_000)

        mock_client = MagicMock()
        mock_podcastfy = types.ModuleType("podcastfy")
        mock_podcastfy.client = mock_client
        mock_client.generate_podcast = MagicMock(return_value=mock_audio_path)

        mock_chain = MagicMock()

        from src.tasks.podcast_generation import generate_podcast_task

        with (
            patch.dict(sys.modules, {"podcastfy": mock_podcastfy, "podcastfy.client": mock_client}),
            patch("src.tasks.podcast_generation.os.path.getsize", return_value=2000),
            patch("src.tasks.podcast_generation.AudioSegment") as mock_audio_cls,
            patch("src.tasks.podcast_generation.build_generation_workflow", return_value=mock_chain) as mock_builder,
            patch("src.tasks.podcast_generation.finalize_episode_generation_task"),
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=_mock_session_with_episode()),
        ):
            mock_audio_cls.from_file.return_value = mock_audio_segment

            result = _invoke_task(
                generate_podcast_task,
                episode_id=episode_id,
                urls=["https://example.com"],
                enable_composition=False,
                enable_distribution=True,
                platforms=platforms,
            )

        assert result["status"] == "success"
        mock_builder.assert_called_once()
        call_kwargs = mock_builder.call_args.kwargs
        assert call_kwargs["enable_distribution"] is True
        assert call_kwargs["platforms"] == platforms
        mock_chain.apply_async.assert_called_once()

    def test_generation_metadata_persisted_before_workflow_dispatch(self):
        """File metadata is written to the Episode before the workflow chain runs.

        The workflow callbacks only persist S3 fields, so distribution/composition
        runs would otherwise lose file_path/transcript_path/duration_seconds/
        file_size_bytes that the default finalize path records (issue #211).
        """
        import sys
        import types

        episode_id = str(uuid.uuid4())
        platforms = {"webhook": {"url": "https://hook.example.com"}}

        mock_audio_segment = MagicMock()
        mock_audio_segment.__len__ = MagicMock(return_value=120_000)  # 120.0s

        mock_client = MagicMock()
        mock_podcastfy = types.ModuleType("podcastfy")
        mock_podcastfy.client = mock_client
        mock_client.generate_podcast = MagicMock(return_value="/tmp/dist_meta.mp3")

        mock_episode = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_episode
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        from src.tasks.podcast_generation import generate_podcast_task

        with (
            patch.dict(sys.modules, {"podcastfy": mock_podcastfy, "podcastfy.client": mock_client}),
            patch("src.tasks.podcast_generation.os.path.getsize", return_value=2000),
            patch("src.tasks.podcast_generation.AudioSegment") as mock_audio_cls,
            patch("src.tasks.podcast_generation.build_generation_workflow", return_value=MagicMock()),
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=mock_session),
        ):
            mock_audio_cls.from_file.return_value = mock_audio_segment
            result = _invoke_task(
                generate_podcast_task,
                episode_id=episode_id,
                urls=["https://example.com"],
                enable_composition=False,
                enable_distribution=True,
                platforms=platforms,
            )

        assert result["status"] == "success"
        assert mock_episode.file_path == "/tmp/dist_meta.mp3"
        assert mock_episode.duration_seconds == 120.0
        assert mock_episode.file_size_bytes == 2000
        mock_session.commit.assert_called_once()

    def test_finalize_task_used_when_no_composition_or_distribution(self):
        """Default path (no composition, no distribution) uses finalize_episode_generation_task."""
        import sys
        import types

        episode_id = str(uuid.uuid4())
        mock_audio_path = "/tmp/simple.mp3"

        mock_audio_segment = MagicMock()
        mock_audio_segment.__len__ = MagicMock(return_value=60_000)

        mock_client = MagicMock()
        mock_podcastfy = types.ModuleType("podcastfy")
        mock_podcastfy.client = mock_client
        mock_client.generate_podcast = MagicMock(return_value=mock_audio_path)

        from src.tasks.podcast_generation import generate_podcast_task

        with (
            patch.dict(sys.modules, {"podcastfy": mock_podcastfy, "podcastfy.client": mock_client}),
            patch("src.tasks.podcast_generation.os.path.getsize", return_value=1000),
            patch("src.tasks.podcast_generation.AudioSegment") as mock_audio_cls,
            patch("src.tasks.podcast_generation.build_generation_workflow") as mock_builder,
            patch("src.tasks.podcast_generation.finalize_episode_generation_task") as mock_finalize,
        ):
            mock_audio_cls.from_file.return_value = mock_audio_segment

            result = _invoke_task(
                generate_podcast_task,
                episode_id=episode_id,
                urls=["https://example.com"],
                enable_composition=False,
                enable_distribution=False,
            )

        assert result["status"] == "success"
        # Workflow chain should NOT be used
        mock_builder.assert_not_called()
        # Simple finalization task should be used
        mock_finalize.delay.assert_called_once()

    def test_finalize_task_used_when_distribution_enabled_but_no_platforms(self):
        """enable_distribution=True but platforms=None falls back to finalize task."""
        import sys
        import types

        episode_id = str(uuid.uuid4())
        mock_audio_path = "/tmp/no_platforms.mp3"

        mock_audio_segment = MagicMock()
        mock_audio_segment.__len__ = MagicMock(return_value=60_000)

        mock_client = MagicMock()
        mock_podcastfy = types.ModuleType("podcastfy")
        mock_podcastfy.client = mock_client
        mock_client.generate_podcast = MagicMock(return_value=mock_audio_path)

        from src.tasks.podcast_generation import generate_podcast_task

        with (
            patch.dict(sys.modules, {"podcastfy": mock_podcastfy, "podcastfy.client": mock_client}),
            patch("src.tasks.podcast_generation.os.path.getsize", return_value=1000),
            patch("src.tasks.podcast_generation.AudioSegment") as mock_audio_cls,
            patch("src.tasks.podcast_generation.build_generation_workflow") as mock_builder,
            patch("src.tasks.podcast_generation.finalize_episode_generation_task") as mock_finalize,
        ):
            mock_audio_cls.from_file.return_value = mock_audio_segment

            result = _invoke_task(
                generate_podcast_task,
                episode_id=episode_id,
                urls=["https://example.com"],
                enable_distribution=True,
                platforms=None,  # No platforms configured
            )

        assert result["status"] == "success"
        mock_builder.assert_not_called()
        mock_finalize.delay.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: build_generation_workflow chain structure
# ---------------------------------------------------------------------------

class TestWorkflowChainStructure:
    """Verify build_generation_workflow builds the correct task chain."""

    def test_upload_only_chain(self):
        """Default chain contains only the S3 upload task."""
        from celery import chain as celery_chain
        from src.tasks.podcast_generation import build_generation_workflow

        with patch("src.tasks.podcast_generation.settings") as mock_settings:
            mock_settings.AWS_S3_BUCKET = "test-bucket"
            workflow = build_generation_workflow(
                user_id="test-user-id",
                episode_id=str(uuid.uuid4()),
                audio_file_path="/tmp/podcast.mp3",
            )

        assert isinstance(workflow, celery_chain)
        task_names = [t.task for t in workflow.tasks]
        assert "upload_to_s3" in task_names
        assert "merge_audio_snippets" not in task_names
        assert "distribute_to_platform" not in task_names

    def test_composition_added_when_enabled(self):
        """merge_audio_snippets is in chain when enable_composition=True."""
        from src.tasks.podcast_generation import build_generation_workflow

        with patch("src.tasks.podcast_generation.settings") as mock_settings:
            mock_settings.AWS_S3_BUCKET = "bucket"
            workflow = build_generation_workflow(
                user_id="test-user-id",
                episode_id=str(uuid.uuid4()),
                audio_file_path="/tmp/audio.mp3",
                enable_composition=True,
                composition_timeline=[],
            )

        task_names = [t.task for t in workflow.tasks]
        assert "merge_audio_snippets" in task_names

    def test_composition_excluded_when_disabled(self):
        """merge_audio_snippets is NOT in chain when enable_composition=False."""
        from src.tasks.podcast_generation import build_generation_workflow

        with patch("src.tasks.podcast_generation.settings") as mock_settings:
            mock_settings.AWS_S3_BUCKET = "bucket"
            workflow = build_generation_workflow(
                user_id="test-user-id",
                episode_id=str(uuid.uuid4()),
                audio_file_path="/tmp/audio.mp3",
                enable_composition=False,
            )

        task_names = [t.task for t in workflow.tasks]
        assert "merge_audio_snippets" not in task_names

    def test_distribution_tasks_for_each_platform(self):
        """One distribute_to_platform task per platform when distribution enabled."""
        from src.tasks.podcast_generation import build_generation_workflow

        platforms = {
            "spotify": {"oauth_tokens": {}},
            "apple_podcasts": {"credentials": {}},
            "webhook": {"url": "https://hook.example.com"},
        }

        with patch("src.tasks.podcast_generation.settings") as mock_settings:
            mock_settings.AWS_S3_BUCKET = "bucket"
            workflow = build_generation_workflow(
                user_id="test-user-id",
                episode_id=str(uuid.uuid4()),
                audio_file_path="/tmp/audio.mp3",
                enable_distribution=True,
                platforms=platforms,
            )

        task_names = [t.task for t in workflow.tasks]
        assert task_names.count("distribute_to_platform") == 3

    def test_chain_stages_are_immutable_signatures(self):
        """Composition/distribution stages must use immutable (.si) signatures.

        In a Celery chain a mutable .s() signature has the previous task's return
        value prepended as the first positional arg, which would collide with the
        keyword episode_id and raise at runtime (issue #211). Each stage re-reads
        the Episode from the DB, so it must ignore the prior result.
        """
        from src.tasks.podcast_generation import build_generation_workflow

        platforms = {
            "spotify": {"oauth_tokens": {}},
            "webhook": {"url": "https://hook.example.com"},
        }

        with patch("src.tasks.podcast_generation.settings") as mock_settings:
            mock_settings.AWS_S3_BUCKET = "bucket"
            workflow = build_generation_workflow(
                user_id="test-user-id",
                episode_id=str(uuid.uuid4()),
                audio_file_path="/tmp/audio.mp3",
                enable_composition=True,
                enable_distribution=True,
                platforms=platforms,
            )

        for task_sig in workflow.tasks:
            if task_sig.task in ("merge_audio_snippets", "distribute_to_platform"):
                assert task_sig.immutable is True, (
                    f"{task_sig.task} must be an immutable (.si) chain signature"
                )

    def test_composition_uploaded_and_distributed(self):
        """With composition enabled, upload targets the composed file and runs
        before distribution, so the distributed artifact is the composed audio
        (issue #211). Distribution metadata is empty — it is read from the Episode
        at runtime.
        """
        from src.tasks.podcast_generation import build_generation_workflow

        episode_id = str(uuid.uuid4())
        composed = f"/tmp/composed_{episode_id}.mp3"
        with patch("src.tasks.podcast_generation.settings") as mock_settings:
            mock_settings.AWS_S3_BUCKET = "bucket"
            workflow = build_generation_workflow(
                user_id="test-user-id",
                episode_id=episode_id,
                audio_file_path="/tmp/original.mp3",
                enable_composition=True,
                enable_distribution=True,
                platforms={"webhook": {"url": "https://hook.example.com"}},
            )

        names = [t.task for t in workflow.tasks]
        # Order: compose → upload → distribute.
        assert names.index("merge_audio_snippets") < names.index("upload_to_s3")
        assert names.index("upload_to_s3") < names.index("distribute_to_platform")

        upload_task = next(t for t in workflow.tasks if t.task == "upload_to_s3")
        assert upload_task.kwargs["file_path"] == composed

        dist_task = next(t for t in workflow.tasks if t.task == "distribute_to_platform")
        assert dist_task.kwargs["episode_metadata"] == {}

    def test_distribution_excluded_when_no_platforms(self):
        """distribute_to_platform not included when platforms is empty/None."""
        from src.tasks.podcast_generation import build_generation_workflow

        with patch("src.tasks.podcast_generation.settings") as mock_settings:
            mock_settings.AWS_S3_BUCKET = "bucket"
            workflow = build_generation_workflow(
                user_id="test-user-id",
                episode_id=str(uuid.uuid4()),
                audio_file_path="/tmp/audio.mp3",
                enable_distribution=True,
                platforms={},  # Empty platforms dict
            )

        task_names = [t.task for t in workflow.tasks]
        assert "distribute_to_platform" not in task_names

    def test_s3_key_contains_episode_id(self):
        """Generated S3 key is namespaced under the user tenant prefix and
        includes the episode_id for uniqueness (issue #215)."""
        from src.tasks.podcast_generation import build_generation_workflow

        episode_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        with patch("src.tasks.podcast_generation.settings") as mock_settings:
            mock_settings.AWS_S3_BUCKET = "bucket"
            workflow = build_generation_workflow(
                user_id=user_id,
                episode_id=episode_id,
                audio_file_path="/tmp/audio.mp3",
            )

        upload_task = workflow.tasks[0]
        s3_key = upload_task.kwargs.get("s3_key", "")
        assert s3_key.startswith(f"podcasts/user-{user_id}/")
        assert episode_id in s3_key

    def test_workflow_key_matches_canonical_helper(self):
        """Acceptance criterion (issue #215): the workflow-chain upload path
        produces the same key as the canonical helper used by the finalize
        path, so both paths agree on the tenant-namespaced layout."""
        from src.tasks.podcast_generation import (
            build_generation_workflow,
            build_podcast_s3_key,
        )

        episode_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        with patch("src.tasks.podcast_generation.settings") as mock_settings:
            mock_settings.AWS_S3_BUCKET = "bucket"
            workflow = build_generation_workflow(
                user_id=user_id,
                episode_id=episode_id,
                audio_file_path="/tmp/audio.mp3",
            )

        upload_task = workflow.tasks[0]
        assert upload_task.kwargs.get("s3_key") == build_podcast_s3_key(
            user_id, episode_id
        )

    def test_explicit_s3_bucket_overrides_settings(self):
        """Explicit s3_bucket parameter takes precedence over settings.AWS_S3_BUCKET."""
        from src.tasks.podcast_generation import build_generation_workflow

        with patch("src.tasks.podcast_generation.settings") as mock_settings:
            mock_settings.AWS_S3_BUCKET = "default-bucket"
            workflow = build_generation_workflow(
                user_id="test-user-id",
                episode_id=str(uuid.uuid4()),
                audio_file_path="/tmp/audio.mp3",
                s3_bucket="override-bucket",
            )

        upload_task = workflow.tasks[0]
        assert upload_task.kwargs.get("bucket_name") == "override-bucket"


# ---------------------------------------------------------------------------
# Test 3: Conditional composition
# ---------------------------------------------------------------------------

class TestConditionalComposition:
    """Verify composition stage is properly conditional."""

    def test_generate_task_passes_composition_timeline(self):
        """Task passes composition_timeline to build_generation_workflow."""
        import sys
        import types

        episode_id = str(uuid.uuid4())
        timeline = [
            {"file_path": "/tmp/intro.mp3", "normalize": True},
            {"file_path": "/tmp/body.mp3", "fade_out_ms": 500},
        ]

        mock_audio_segment = MagicMock()
        mock_audio_segment.__len__ = MagicMock(return_value=60_000)

        mock_client = MagicMock()
        mock_podcastfy = types.ModuleType("podcastfy")
        mock_podcastfy.client = mock_client
        mock_client.generate_podcast = MagicMock(return_value="/tmp/audio.mp3")

        mock_chain = MagicMock()

        from src.tasks.podcast_generation import generate_podcast_task

        with (
            patch.dict(sys.modules, {"podcastfy": mock_podcastfy, "podcastfy.client": mock_client}),
            patch("src.tasks.podcast_generation.os.path.getsize", return_value=1000),
            patch("src.tasks.podcast_generation.AudioSegment") as mock_audio_cls,
            patch("src.tasks.podcast_generation.build_generation_workflow", return_value=mock_chain) as mock_builder,
            patch("src.tasks.podcast_generation.finalize_episode_generation_task"),
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=_mock_session_with_episode()),
        ):
            mock_audio_cls.from_file.return_value = mock_audio_segment

            _invoke_task(
                generate_podcast_task,
                episode_id=episode_id,
                urls=["https://example.com"],
                enable_composition=True,
                composition_timeline=timeline,
            )

        call_kwargs = mock_builder.call_args.kwargs
        assert call_kwargs["composition_timeline"] == timeline


# ---------------------------------------------------------------------------
# Test 4: Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Verify errors in generate_podcast_task don't trigger workflow chain."""

    def test_workflow_chain_not_called_on_generation_failure(self):
        """If podcast generation fails, build_generation_workflow is never called."""
        import sys
        import types

        episode_id = str(uuid.uuid4())

        mock_client = MagicMock()
        mock_podcastfy = types.ModuleType("podcastfy")
        mock_podcastfy.client = mock_client
        mock_client.generate_podcast = MagicMock(side_effect=RuntimeError("LLM API error"))

        from src.tasks.podcast_generation import generate_podcast_task

        with (
            patch.dict(sys.modules, {"podcastfy": mock_podcastfy, "podcastfy.client": mock_client}),
            patch("src.tasks.podcast_generation.build_generation_workflow") as mock_builder,
            patch("src.tasks.podcast_generation.finalize_episode_generation_task"),
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=_mock_session_with_episode()),
            patch.object(
                generate_podcast_task,
                "retry",
                side_effect=generate_podcast_task.MaxRetriesExceededError(),
            ),
        ):
            result = _invoke_task(
                generate_podcast_task,
                episode_id=episode_id,
                urls=["https://example.com"],
                enable_composition=True,
            )

        assert result["status"] == "failed"
        mock_builder.assert_not_called()

    def test_broker_error_during_workflow_dispatch_does_not_fail_generation(self):
        """A broker failure when dispatching the workflow chain does not change generation result."""
        import sys
        import types

        episode_id = str(uuid.uuid4())
        mock_audio_path = "/tmp/podcast.mp3"

        mock_audio_segment = MagicMock()
        mock_audio_segment.__len__ = MagicMock(return_value=60_000)

        mock_client = MagicMock()
        mock_podcastfy = types.ModuleType("podcastfy")
        mock_podcastfy.client = mock_client
        mock_client.generate_podcast = MagicMock(return_value=mock_audio_path)

        mock_chain = MagicMock()
        mock_chain.apply_async.side_effect = ConnectionError("Redis unavailable")

        from src.tasks.podcast_generation import generate_podcast_task

        with (
            patch.dict(sys.modules, {"podcastfy": mock_podcastfy, "podcastfy.client": mock_client}),
            patch("src.tasks.podcast_generation.os.path.getsize", return_value=1000),
            patch("src.tasks.podcast_generation.AudioSegment") as mock_audio_cls,
            patch("src.tasks.podcast_generation.build_generation_workflow", return_value=mock_chain),
            patch("src.tasks.podcast_generation.finalize_episode_generation_task"),
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=_mock_session_with_episode()),
        ):
            mock_audio_cls.from_file.return_value = mock_audio_segment

            # Even though the broker is down, generation result should still be success
            result = _invoke_task(
                generate_podcast_task,
                episode_id=episode_id,
                urls=["https://example.com"],
                enable_composition=True,
            )

        assert result["status"] == "success"

    def test_workflow_dispatch_skipped_when_user_id_unresolved(self):
        """Fail closed: if the episode/user_id cannot be resolved, the upload
        chain is never dispatched, so nothing is written outside the
        podcasts/user-*/ tenant prefix (issue #215)."""
        import sys
        import types

        episode_id = str(uuid.uuid4())

        mock_audio_segment = MagicMock()
        mock_audio_segment.__len__ = MagicMock(return_value=60_000)

        mock_client = MagicMock()
        mock_podcastfy = types.ModuleType("podcastfy")
        mock_podcastfy.client = mock_client
        mock_client.generate_podcast = MagicMock(return_value="/tmp/audio.mp3")

        # Lookup returns no episode → user_id stays unresolved.
        mock_session = MagicMock()
        mock_session.get.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        from src.tasks.podcast_generation import generate_podcast_task

        with (
            patch.dict(sys.modules, {"podcastfy": mock_podcastfy, "podcastfy.client": mock_client}),
            patch("src.tasks.podcast_generation.os.path.getsize", return_value=1000),
            patch("src.tasks.podcast_generation.AudioSegment") as mock_audio_cls,
            patch("src.tasks.podcast_generation.build_generation_workflow") as mock_builder,
            patch("src.tasks.podcast_generation.finalize_episode_generation_task"),
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=mock_session),
        ):
            mock_audio_cls.from_file.return_value = mock_audio_segment
            result = _invoke_task(
                generate_podcast_task,
                episode_id=episode_id,
                urls=["https://example.com"],
                enable_composition=True,
            )

        # Generation itself still succeeded; only the unsafe dispatch was skipped.
        assert result["status"] == "success"
        mock_builder.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: Multiple platform distribution
# ---------------------------------------------------------------------------

class TestMultiplePlatformDistribution:
    """Verify multi-platform distribution creates parallel tasks."""

    def test_two_platforms_create_two_distribution_tasks(self):
        """Each configured platform gets its own distribute_to_platform task."""
        from src.tasks.podcast_generation import build_generation_workflow

        platforms = {
            "spotify": {"oauth_tokens": {"access_token": "tok"}},
            "webhook": {"url": "https://hook.example.com"},
        }

        with patch("src.tasks.podcast_generation.settings") as mock_settings:
            mock_settings.AWS_S3_BUCKET = "bucket"
            workflow = build_generation_workflow(
                user_id="test-user-id",
                episode_id=str(uuid.uuid4()),
                audio_file_path="/tmp/audio.mp3",
                enable_distribution=True,
                platforms=platforms,
            )

        dist_tasks = [t for t in workflow.tasks if t.task == "distribute_to_platform"]
        assert len(dist_tasks) == 2
        platform_names = {t.kwargs.get("platform") for t in dist_tasks}
        assert platform_names == {"spotify", "webhook"}

    def test_distribution_tasks_include_episode_metadata(self):
        """Each distribution task has episode_id in kwargs."""
        from src.tasks.podcast_generation import build_generation_workflow

        episode_id = str(uuid.uuid4())
        platforms = {"spotify": {}}

        with patch("src.tasks.podcast_generation.settings") as mock_settings:
            mock_settings.AWS_S3_BUCKET = "bucket"
            workflow = build_generation_workflow(
                user_id="test-user-id",
                episode_id=episode_id,
                audio_file_path="/tmp/audio.mp3",
                enable_distribution=True,
                platforms=platforms,
            )

        dist_task = next(t for t in workflow.tasks if t.task == "distribute_to_platform")
        assert dist_task.kwargs.get("episode_id") == episode_id


# ---------------------------------------------------------------------------
# Test 6: Episode model has new fields
# ---------------------------------------------------------------------------

class TestEpisodeModelWorkflowFields:
    """Verify the Episode model has the workflow tracking fields."""

    def test_episode_model_has_platform_ids(self):
        """Episode model includes platform_ids column."""
        from src.models.episode import Episode
        assert hasattr(Episode, "platform_ids"), "Episode must have platform_ids column"

    def test_episode_model_has_error_message(self):
        """Episode model includes error_message column."""
        from src.models.episode import Episode
        assert hasattr(Episode, "error_message"), "Episode must have error_message column"

    def test_episode_schema_exposes_platform_ids(self):
        """EpisodeResponse schema includes platform_ids field."""
        from src.schemas.episode import EpisodeResponse
        assert "platform_ids" in EpisodeResponse.model_fields

    def test_episode_schema_exposes_error_message(self):
        """EpisodeResponse schema includes error_message field."""
        from src.schemas.episode import EpisodeResponse
        assert "error_message" in EpisodeResponse.model_fields


# ---------------------------------------------------------------------------
# Test 7: Config settings
# ---------------------------------------------------------------------------

class TestWorkflowConfigSettings:
    """Verify workflow feature flags are present in settings."""

    def test_enable_audio_composition_setting_exists(self):
        """Settings has ENABLE_AUDIO_COMPOSITION flag, defaulting to False."""
        from src.config import Settings
        # Pydantic v2 stores fields in model_fields
        assert "ENABLE_AUDIO_COMPOSITION" in Settings.model_fields
        # Create a minimal settings instance to verify the default value
        import os
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql+asyncpg://x:x@localhost/x",
            "ENCRYPTION_KEY": "a" * 32,
            "JWT_SECRET_KEY": "test",
        }):
            s = Settings()
            assert s.ENABLE_AUDIO_COMPOSITION is False

    def test_enable_platform_distribution_setting_exists(self):
        """Settings has ENABLE_PLATFORM_DISTRIBUTION flag, defaulting to False."""
        from src.config import Settings
        assert "ENABLE_PLATFORM_DISTRIBUTION" in Settings.model_fields
        import os
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql+asyncpg://x:x@localhost/x",
            "ENCRYPTION_KEY": "a" * 32,
            "JWT_SECRET_KEY": "test",
        }):
            s = Settings()
            assert s.ENABLE_PLATFORM_DISTRIBUTION is False


# ---------------------------------------------------------------------------
# Test 8: generate_podcast_task parameter acceptance
# ---------------------------------------------------------------------------

class TestGeneratePodcastTaskWorkflowParameters:
    """Verify generate_podcast_task signature has workflow parameters."""

    def test_task_accepts_enable_composition(self):
        """generate_podcast_task must accept enable_composition parameter."""
        import inspect
        from src.tasks.podcast_generation import generate_podcast_task
        sig = inspect.signature(generate_podcast_task.run)
        assert "enable_composition" in sig.parameters

    def test_task_accepts_enable_distribution(self):
        """generate_podcast_task must accept enable_distribution parameter."""
        import inspect
        from src.tasks.podcast_generation import generate_podcast_task
        sig = inspect.signature(generate_podcast_task.run)
        assert "enable_distribution" in sig.parameters

    def test_task_accepts_platforms(self):
        """generate_podcast_task must accept platforms parameter."""
        import inspect
        from src.tasks.podcast_generation import generate_podcast_task
        sig = inspect.signature(generate_podcast_task.run)
        assert "platforms" in sig.parameters

    def test_task_accepts_composition_timeline(self):
        """generate_podcast_task must accept composition_timeline parameter."""
        import inspect
        from src.tasks.podcast_generation import generate_podcast_task
        sig = inspect.signature(generate_podcast_task.run)
        assert "composition_timeline" in sig.parameters

    def test_workflow_params_default_to_disabled(self):
        """All workflow params default to disabled/None."""
        import inspect
        from src.tasks.podcast_generation import generate_podcast_task
        sig = inspect.signature(generate_podcast_task.run)
        assert sig.parameters["enable_composition"].default is False
        assert sig.parameters["enable_distribution"].default is False
        assert sig.parameters["platforms"].default is None
        assert sig.parameters["composition_timeline"].default is None


# ---------------------------------------------------------------------------
# Issue #294: every in-task failure path must write a terminal DB status so the
# episode never stays stuck at 'queued'.
# ---------------------------------------------------------------------------
class TestFailurePathsWriteDbStatus:
    def test_soft_time_limit_writes_failed(self):
        """SoftTimeLimitExceeded persists generation_status='failed' to the DB."""
        from celery.exceptions import SoftTimeLimitExceeded
        from src.tasks import podcast_generation as pg

        ep_id = str(uuid.uuid4())
        pg.generate_podcast_task.request.update(id="soft-tl", retries=0)
        with patch("podcastfy.client.generate_podcast", side_effect=SoftTimeLimitExceeded()), \
             patch.object(pg.generate_podcast_task, "update_state", MagicMock()), \
             patch("src.tasks.podcast_generation._update_episode") as mock_upd:
            result = pg.generate_podcast_task.run(episode_id=ep_id)

        assert result["status"] == "failed"
        mock_upd.assert_called_once()
        assert mock_upd.call_args.kwargs["updates"]["generation_status"] == "failed"

    def test_retry_exhaustion_writes_failed(self):
        """When retries are exhausted, the episode is marked 'failed' in the DB."""
        from src.tasks import podcast_generation as pg

        ep_id = str(uuid.uuid4())
        task = pg.generate_podcast_task
        task.request.update(id="retry-exh")
        # Force retry() to signal exhaustion so we exercise the MaxRetriesExceeded
        # branch directly (eager retry would otherwise re-invoke the task inline).
        with patch("podcastfy.client.generate_podcast", side_effect=RuntimeError("boom")), \
             patch.object(task, "update_state", MagicMock()), \
             patch.object(task, "retry", side_effect=task.MaxRetriesExceededError()), \
             patch("src.tasks.podcast_generation._update_episode") as mock_upd:
            result = task.run(episode_id=ep_id)

        assert result["status"] == "failed"
        mock_upd.assert_called_once()
        assert mock_upd.call_args.kwargs["updates"]["generation_status"] == "failed"
