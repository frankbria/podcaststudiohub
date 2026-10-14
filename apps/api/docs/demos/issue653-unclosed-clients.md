# #653 — a live ElevenLabs run leaks no socket or file handle

*2026-10-14T04:25:08Z by Showboat 0.6.1*
<!-- showboat-id: e22509b2-7a92-46d9-876d-f8662fdf3e28 -->

The live module used to ignore PytestUnraisableExceptionWarning: the backend never closed its SDK client's socket. With that ignore removed, the run also exposed a second leak in every backend's final step: pydub's export returns the output file it opened, still open. Both are fixed; the live run passes under the repo's warnings-as-errors config with no ignore (real ElevenLabs API, key from the root .env):

```bash
. /home/frankbria/.claude/jobs/a14abad9/tmp/testenv.sh && grep -c filterwarnings tests/unit/test_engine_tts_live.py; RUN_LIVE_TTS_TESTS=1 $PY -m pytest tests/unit/test_engine_tts_live.py -k elevenlabs --no-cov -p no:cacheprovider -q 2>&1 | tail -1 | sed 's/ in .*//'
```

```output
0
======================= 1 passed, 1 deselected
```

Unit tests pin both closes:

```bash
. /home/frankbria/.claude/jobs/a14abad9/tmp/testenv.sh && $PY -m pytest tests/unit/test_engine_tts.py --no-cov -p no:cacheprovider -q -v -k 'closes_its_http_client or exported_file_handle' 2>&1 | grep -E 'PASSED|FAILED' | sed 's/ *\[[0-9]*%\]//; s/.*:://'
```

```output
test_elevenlabs_closes_its_http_client_after_synthesis PASSED [ 50%]
test_the_exported_file_handle_is_closed PASSED
```
