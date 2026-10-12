# #543 (PR A) — a real episode generated through the in-repo engine

*2026-10-12T17:23:29Z by Showboat 0.6.1*
<!-- showboat-id: 7ab4e1dd-1c85-4db6-9d3e-bf6c0bd331ef -->

One episode, end to end, through the real `generate_podcast_task` body with `ENGINE=native` (the new default): real Gemini scripting, real OpenAI TTS, real Postgres, real local storage (no bucket configured). The episode carries an **ElevenLabs** TTS configuration (eleven_v3, Text-to-Dialogue), the provider podcastfy could not reach after #542; the router still sends podcastfy's `tts_model`, which the native path ignores in favour of the stored row. (The unconfigured default-voices path is covered against the real database in `tests/test_native_inputs.py`; OpenAI's speech endpoint was answering in ~56s per sentence from this host on 2026-10-12, too slow for a full episode.) Two seams are adjusted, both printed in the script: `update_state` prints instead of reporting to a result backend (`.run()` has no Celery request), and `finalize`'s `.delay` runs the same task body inline instead of waiting for a worker. Driver: `/tmp/demo_543.py`; keys load from the root `.env` via `/tmp/demo543env.sh` and are never printed.

```bash
. /tmp/demo543env.sh && .venv/bin/python /tmp/demo_543.py /tmp/demo543-storage 2>&1 | grep -v '^{' | grep -v '^WARNING\|^INFO'
```

```output
ENGINE=native  LLM=gemini/gemini-3.5-flash
episode fc5c0066-28d3-4955-bb2b-470cccc0f34e: no TTS config set (episode or project)
  progress extraction   0%
  progress extraction  33%
  progress transcript  33%
  progress transcript  66%
  progress audio       66%
  progress retrying     0%
Traceback (most recent call last):
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpx/_transports/default.py", line 72, in map_httpcore_exceptions
    yield
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpx/_transports/default.py", line 236, in handle_request
    resp = self._pool.handle_request(req)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpcore/_sync/connection_pool.py", line 256, in handle_request
    raise exc from None
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpcore/_sync/connection_pool.py", line 236, in handle_request
    response = connection.handle_request(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpcore/_sync/connection.py", line 103, in handle_request
    return self._connection.handle_request(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpcore/_sync/http11.py", line 136, in handle_request
    raise exc
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpcore/_sync/http11.py", line 106, in handle_request
    ) = self._receive_response_headers(**kwargs)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpcore/_sync/http11.py", line 177, in _receive_response_headers
    event = self._receive_event(timeout=timeout)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpcore/_sync/http11.py", line 217, in _receive_event
    data = self._network_stream.read(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpcore/_backends/sync.py", line 126, in read
    with map_exceptions(exc_map):
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpcore/_exceptions.py", line 14, in map_exceptions
    raise to_exc(exc) from exc
httpcore.ReadTimeout: The read operation timed out

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/openai/_base_client.py", line 982, in request
    response = self._client.send(
               ^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpx/_client.py", line 926, in send
    response = self._send_handling_auth(
               ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpx/_client.py", line 954, in _send_handling_auth
    response = self._send_handling_redirects(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpx/_client.py", line 991, in _send_handling_redirects
    response = self._send_single_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpx/_client.py", line 1027, in _send_single_request
    response = transport.handle_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpx/_transports/default.py", line 235, in handle_request
    with map_httpcore_exceptions():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/httpx/_transports/default.py", line 89, in map_httpcore_exceptions
    raise mapped_exc(message) from exc
httpx.ReadTimeout: The read operation timed out

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/src/engine/tts/openai.py", line 65, in render
    response = client.audio.speech.create(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/openai/resources/audio/speech.py", line 103, in create
    return self._post(
           ^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/openai/_base_client.py", line 1259, in post
    return cast(ResponseT, self.request(cast_to, opts, stream=stream, stream_cls=stream_cls))
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/openai/_base_client.py", line 1000, in request
    raise APITimeoutError(request=request) from err
openai.APITimeoutError: Request timed out.

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/tmp/demo_543.py", line 64, in <module>
    result = generate_podcast_task.run(
             ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/src/tasks/podcast_generation.py", line 846, in generate_podcast_task
    _retry_or_fail(self, e, episode_id, task_id, run_dir, lock_held)
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/src/tasks/podcast_generation.py", line 722, in _retry_or_fail
    raise task.retry(exc=e, countdown=calculate_backoff(task.request.retries))
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/.venv/lib/python3.12/site-packages/celery/app/task.py", line 753, in retry
    raise_with_context(exc or Retry('Task can be retried', None))
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/src/tasks/podcast_generation.py", line 810, in generate_podcast_task
    audio_file_path, transcript_path = _generate_audio(
                                       ^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/src/tasks/podcast_generation.py", line 354, in _generate_audio
    return _run_native_engine(
           ^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/src/tasks/podcast_generation.py", line 422, in _run_native_engine
    audio_path = synthesise(tts_provider, script, tts_config, Path(run_dir))
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/src/engine/tts/__init__.py", line 36, in synthesise
    return get_backend(provider).synthesise(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/src/engine/tts/openai.py", line 76, in synthesise
    segments = synthesise_concurrently(render, turns)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/src/engine/tts/openai.py", line 93, in synthesise_concurrently
    return list(pool.map(render, turns))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/concurrent/futures/_base.py", line 619, in result_iterator
    yield _result_or_cancel(fs.pop())
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/concurrent/futures/_base.py", line 317, in _result_or_cancel
    return fut.result(timeout)
           ^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/concurrent/futures/_base.py", line 456, in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/concurrent/futures/_base.py", line 401, in __get_result
    raise self._exception
  File "/usr/lib/python3.12/concurrent/futures/thread.py", line 58, in run
    result = self.fn(*self.args, **self.kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/frankbria/projects/worktrees/issue-543-engine-cutover/apps/api/src/engine/tts/openai.py", line 73, in render
    raise TTSProviderError(f"OpenAI TTS call failed: {exc}") from exc
src.engine.tts.base.TTSProviderError: OpenAI TTS call failed: Request timed out.
```

```bash
. /tmp/demo543env.sh && .venv/bin/python /tmp/demo_543.py /tmp/demo543-storage 2>&1 | grep -v '^{' | grep -v '^WARNING\|^INFO'
```

```output
ENGINE=native  LLM=gemini/gemini-3.5-flash
episode e4fdab79-acd7-44ff-9f30-9561d555dac1: TTS config on the episode = elevenlabs / eleven_v3 (Text-to-Dialogue)
  progress extraction   0%
  progress extraction  33%
  progress transcript  33%
  progress transcript  66%
  progress audio       66%
  progress complete   100%
task result: status=success
episode row: generation_status=complete
  file_path       = episode-e4fdab79-acd7-44ff-9f30-9561d555dac1.mp3 (under storage)
  transcript_path = episode-e4fdab79-acd7-44ff-9f30-9561d555dac1.transcript.json (under storage)
  duration=93.0s  size=2234453 bytes
transcript: title='Demystifying Retrieval-Augmented Generation' turns=11 speakers=['guest', 'host']
  first turn: host: Welcome to PODCASTIFY! Today we are diving into Retrieval-Augmented Generation, or RAG, wh...
ffprobe: format_name=mp3 duration=93.074286
```

| PR A plan item (#543 comment) | Evidence | Status |
|---|---|---|
| Engine is the default; podcastfy is the rollback | Run above prints `ENGINE=native`, and podcastfy was never called (unit: `test_native_path_runs_the_engine_end_to_end` asserts it; `test_engine_podcastfy_is_the_rollback_switch` covers the switch) | VERIFIED |
| Raw stored provider/config used, not podcastfy's translation | Router sent `tts_model="elevenlabs"`; audio came from the row's eleven_v3 voices. Real-DB tests in `tests/test_native_inputs.py` (episode > project default > podcastfy default voices) | VERIFIED |
| Real per-part progress instead of fixed markers | transcript 33 to 66 from the engine's callback, then audio 66, then complete 100 | VERIFIED |
| Transcript persisted and on the row | `transcript_path` set (the first non-null value ever); JSON has 11 host/guest turns | VERIFIED |
| Episode completes with real audio | `generation_status=complete`, ffprobe: mp3, 93.07 s, matching `duration_seconds` | VERIFIED |
| ElevenLabs works again (podcastfy path broken since #542) | This run: eleven_v3 Text-to-Dialogue | VERIFIED |
| Transcript deletion routed to S3 when a bucket is set | `test_delete_episode_queues_an_s3_transcript_as_an_s3_deletion` (real DB, real delete flow) plus model routing tests | VERIFIED (test evidence; no bucket on this host) |
