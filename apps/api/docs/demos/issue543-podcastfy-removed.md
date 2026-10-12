# #543 (PR B) — podcastfy removed; the engine runs alone

*2026-10-12T18:56:00Z by Showboat 0.6.1*
<!-- showboat-id: 111a23fc-a6a3-4ac1-8f02-176945c35562 -->

Every command runs from this branch's venv, built from the lockfile **without podcastfy**. Keys load from the root `.env` via `/tmp/demo543b_env.sh` and are never printed. Drivers: `/tmp/demo_543b_checks.py` and `/tmp/demo_543.py` (from PR A, unchanged).

**The old engine's dependency tree is gone**: not installed, not in the lock, and the audit gate blocks on every advisory with empty allowlists.

```bash
. /tmp/demo543b_env.sh && .venv/bin/python /tmp/demo_543b_checks.py absent 2>&1 | grep -v '^{' && uv tree --offline 2>/dev/null | grep -ciE 'langchain|litellm|langsmith|aiplatform|podcastfy' | sed 's/^/uv tree matches for the removed tree: /'
```

```output
podcastfy       installed: False
langchain       installed: False
langchain_core  installed: False
langsmith       installed: False
litellm         installed: False
uv tree matches for the removed tree: 0
```

```bash
bash scripts/security-audit.sh 2>&1 | grep -E 'vulnerabilit|pip-audit gate'
```

```output
No known vulnerabilities found
pip-audit gate: 0 blocking, 0 warn-only (non-blocking)
```

**A real episode end to end** on the final code (Gemini script, ElevenLabs eleven_v3 audio, stored transcript):

```bash
. /tmp/demo543b_env.sh && .venv/bin/python /tmp/demo_543.py /tmp/demo543-storage 2>&1 | grep -v '^{' | grep -v '^WARNING\|^INFO'
```

```output
LLM=gemini/gemini-3.5-flash
episode df05079b-df5c-4b90-878c-836b01dd2ac8: TTS config on the episode = elevenlabs / eleven_v3 (Text-to-Dialogue)
  progress extraction   0%
  progress extraction  33%
  progress transcript  33%
  progress transcript  66%
  progress audio       66%
  progress complete   100%
task result: status=success
episode row: generation_status=complete
  file_path       = episode-df05079b-df5c-4b90-878c-836b01dd2ac8.mp3 (under storage)
  transcript_path = episode-df05079b-df5c-4b90-878c-836b01dd2ac8.transcript.json (under storage)
  duration=93.1s  size=2236334 bytes
transcript: title='Understanding Retrieval-Augmented Generation' turns=9 speakers=['guest', 'host']
  first turn: host: Hello everyone, and welcome to PODCASTIFY! Today we are looking into Retrieval-Augmented G...
ffprobe: format_name=mp3 duration=93.152653
```

**YouTube sources** yield the video's transcript through youtube-transcript-api 1.x (the first video on YouTube):

```bash
. /tmp/demo543b_env.sh && .venv/bin/python /tmp/demo_543b_checks.py youtube https://www.youtube.com/watch?v=jNQXAC9IVRw 2>&1 | grep -v '^{'
```

```output
transcript: 39 words; starts: 'All right, so here we are, in front of the\nelephants the cool thing about these '
```

**Edge TTS still fails** after the bump to edge-tts 7.2.8 (podcastfy capped it below 7): Microsoft returns 403 to this host even with the current client. The version hypothesis in #616 is therefore falsified; #616 stays open.

```bash
. /tmp/demo543b_env.sh && .venv/bin/python /tmp/demo_543b_checks.py edge 2>&1 | grep -E 'TTSProviderError|edge-tts:' | cut -c1-140; true
```

```output
    raise TTSProviderError(f"Edge TTS call failed: {exc}") from exc
src.engine.tts.base.TTSProviderError: Edge TTS call failed: 403, message='Invalid response status', url='wss://speech.platform.bing.com/cons
```

| #543 done-when | Evidence | Status |
|---|---|---|
| `grep -rn podcastfy apps/api/src apps/api/pyproject.toml` returns nothing | No import of, or dependency on, the package remains (above). Remaining lowercase matches are the product's own name (Celery app name, `podcastfy-run-` temp prefix), accurate historical comparisons, and the inert router shim tracked in #623 | MET in intent; deviation stated in the PR |
| No audit suppressions attributable to the old engine | `TRIAGED` and `WARN_ONLY_PACKAGES` empty; real `pip-audit`: no known vulnerabilities | MET |
| `uv tree` shows no `langchain*` or `litellm` | 0 matches (above); `test_the_old_engines_dependency_tree_is_not_installed` enforces it | MET |
| Demo: an episode on ElevenLabs v3 and one on Edge | ElevenLabs v3: real episode above. Edge: 403 from Microsoft on edge-tts 7.2.8 → #616 | ElevenLabs MET; Edge NOT MET (#616) |
| #518 closed as resolved | Closed on merge with this evidence | on merge |
