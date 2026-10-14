# #617 — the opt-in live ElevenLabs test can pass

*2026-10-14T02:59:50Z by Showboat 0.6.1*
<!-- showboat-id: 2bfd8b17-e6ce-4ee4-a901-1d0870ce29c2 -->

Before: the live tests sat in test_engine_tts.py, whose autouse fixtures replace the provider keys with fakes and pydub with a nine-byte export. So besides the placeholder voice ids the issue names, the test sent the key 'test-eleven' (401) and could never meet its own size assertion. They now live in their own module and use two of the account's real voices.

Default run: the fakes still pass and the live tests skip.

```bash
. /home/frankbria/.claude/jobs/a14abad9/tmp/testenv.sh && $PY -m pytest tests/unit/test_engine_tts.py tests/unit/test_engine_tts_live.py --no-cov -p no:cacheprovider -q 2>&1 | tail -1 | sed 's/ in .*//'
```

```output
======================== 103 passed, 2 skipped
```

Opt-in run against the real ElevenLabs API (key from the root .env, scoped to TTS + voices_read):

```bash
. /home/frankbria/.claude/jobs/a14abad9/tmp/testenv.sh && RUN_LIVE_TTS_TESTS=1 $PY -m pytest tests/unit/test_engine_tts_live.py -k elevenlabs --no-cov -p no:cacheprovider -q 2>&1 | tail -1 | sed 's/ in .*//'
```

```output
======================= 1 passed, 1 deselected
```
