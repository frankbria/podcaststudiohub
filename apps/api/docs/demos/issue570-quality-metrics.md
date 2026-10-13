# #570 — quality metrics revived on the in-repo engine

*2026-10-13T02:57:13Z by Showboat 0.6.1*
<!-- showboat-id: 41307408-1b3e-458a-9360-c377bbc7597c -->

Done-when: a generated episode carries non-empty `generation_progress["quality_metrics"]` after the run, and the restored endpoints return it. One episode, end to end, through the real `generate_podcast_task` body: real Gemini scripting, real ElevenLabs (eleven_v3) TTS, real Postgres, real local storage. The metrics are computed from the script's structured turns (`src/engine/quality.py`) and written by the task; nothing is seeded. The three restored `/quality-metrics` routes are then called over ASGI with a real JWT for the episode's owner. Seams, as in the #543 demo: `update_state` prints, and finalize's `.delay` runs the same task body inline instead of waiting for a worker. Driver: `/tmp/demo_570.py` (built on `/tmp/demo_543.py`); keys load from the root `.env` via `/tmp/demo543env.sh` and are never printed.

```bash
. /tmp/demo543env.sh && .venv/bin/python /tmp/demo_570.py /tmp/demo570-storage 2>&1 | grep -v "^{" | grep -v "^WARNING\|^INFO"
```

```output
LLM=gemini/gemini-3.5-flash
episode 1548eb9c-52b9-41ea-82e3-daba99782ac8: TTS config on the episode = elevenlabs / eleven_v3 (Text-to-Dialogue)
  progress extraction   0%
  progress extraction  33%
  progress transcript  33%
  progress transcript  66%
  progress audio       66%
  progress complete   100%
task result: status=success
episode row: generation_status=complete
  file_path       = episode-1548eb9c-52b9-41ea-82e3-daba99782ac8.mp3 (under storage)
  transcript_path = episode-1548eb9c-52b9-41ea-82e3-daba99782ac8.transcript.json (under storage)
  duration=101.2s  size=2430685 bytes
generation_progress.quality_metrics (written by the run):
  tone                       casual
  is_balanced                True
  total_words                255
  dialogue_turns             10
  coherence_score            0.7
  has_good_banter            True
  max_monologue_words        36
  speaker_balance_ratio      1.48
  duration_estimate_minutes  1.7
  calculated_at present: True
GET /quality-metrics/episodes/{id} -> 200
  scores: content_length=0.3 (poor), coherence=0.7 (good), balance=1.0 (excellent), engagement=0.8 (excellent), overall=0.735 (good)
  overall_rating=good
  strengths=['Excellent speaker balance', 'Good dialogue engagement with 10 speaker turns', 'Short, punchy exchanges with no long monologues']
  improvements=['Episode is quite short (1.7 min) - consider adding more content']
GET /quality-metrics/projects/{id} -> 200 analysed=1 distribution={'excellent': 0, 'good': 1, 'fair': 0, 'poor': 0}
GET /quality-metrics/projects/{id}/episodes -> 200 total=1
GET without a token -> 401
transcript: title='Understanding Retrieval-Augmented Generation' turns=11 speakers=['guest', 'host']
  first turn: host: Welcome to PODCASTIFY! Great to have you with us. Today we are unpacking Retrieval-Augment...
ffprobe: format_name=mp3 duration=101.250612
```

Every done-when holds on a real run. The task wrote the metrics (nothing was seeded), the episode route scores them, the project aggregate and list include the episode, and the routes still require auth. The 150-words-per-minute estimate (1.7 min) agrees with the real audio (101 s). The "Welcome to PODCASTIFY!" opening is #621. The demo user, project and episode were deleted afterwards.
