# #620 — a failure after scripting does not buy the script again

*2026-10-13T03:40:43Z by Showboat 0.6.1*
<!-- showboat-id: af922c46-f726-464d-aa15-d3d0366086de -->

Done-when 1, on a real generation: real Gemini script, real ElevenLabs (eleven_v3) TTS, real Postgres, real Redis, and a real S3 API (a throwaway SeaweedFS container reached through boto3's standard `AWS_ENDPOINT_URL`). Attempt 1's synthesis is made to fail once (the injected `TTSProviderError` is the only fake). Attempt 2 runs under the same Celery task id, as a Celery retry does. `generate_script` and `synthesise` are wrapped only to count calls; the real functions run. As in the #543 demo, `update_state` is silenced and finalize's `.delay` runs inline. Driver: `/tmp/demo_620.py`; provider keys load from the root `.env` via `/tmp/demo543env.sh` and are never printed; S3 settings come from `/tmp/demo620_s3env.sh`.

Done-when 2 is the policy written in `src/engine/tts/base.py` (`with_retries`) and enforced by tests. Done-when 3 (transcript upload retries transient S3 errors) is proven by tests that run the real botocore client's retry logic through a `before-send` hook, since a real bucket cannot be made to fail on cue. The run below also shows that the new `Config` works against a real S3 API.

A first recording of this run exposed a separate, older bug: the finalize path calls `upload_to_s3_task` synchronously, with no task id, and Celery's `update_state` raised "task_id must not be empty", so the audio never reached S3 and the episode was marked failed. Fixed in this PR, with a test; the run below is after the fix.

```bash
. /tmp/demo543env.sh && . /tmp/demo620_s3env.sh && .venv/bin/python /tmp/demo_620.py /tmp/unused 2>&1 | grep -v "^{" | grep -v "^WARNING\|^INFO"
```

```output
LLM=gemini/gemini-3.5-flash
episode 175bcc8c-55a4-4539-b690-d6fd15b73828: TTS config on the episode = elevenlabs / eleven_v3 (Text-to-Dialogue)
attempt 1: failed after scripting: injected: speech endpoint timed out
  script kept for the retry: ttl=7435s
attempt 2: status=success
generate_script calls (paid LLM): 1
synthesise calls (paid TTS):      2
episode row: generation_status=complete
  transcript_path = podcasts/user-4e1c5823-e358-42cf-88aa-0f5bc644907c/episode-175bcc8c-55a4-4539-b690-d6fd15b73828.transcript.json
  s3_key          = podcasts/user-4e1c5823-e358-42cf-88aa-0f5bc644907c/episode-175bcc8c-55a4-4539-b690-d6fd15b73828.mp3
  in S3: episode-175bcc8c-55a4-4539-b690-d6fd15b73828.transcript.json 1557 bytes application/json
  in S3: episode-175bcc8c-55a4-4539-b690-d6fd15b73828.mp3 1485889 bytes audio/mpeg
```

Attempt 1 failed after the script was bought; the script was kept under the task id for the retry window (TTL about 2 h, from `(max_retries + 1) × (time limit + 60 s)`). Attempt 2 voiced that same script: **one** paid `generate_script` call for **two** synthesis attempts. The episode completed, with transcript and audio both in S3 (`application/json` and `audio/mpeg`). The demo user, project and episode were deleted afterwards.
