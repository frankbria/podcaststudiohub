# Demo — #376: Composition downloads S3-backed snippets before merging

**Date:** 2026-07-13 · **Branch:** `feat/376-composition-s3-snippet-download`

Real services: real ffmpeg-generated tones, the real S3 bucket
(`podcaststudiohub-audio`, demo prefix `audio-snippets/demo-376/`), and the
actual `merge_audio_snippets_task` code path (`.apply()`, eager). Local snippet
copies were deleted after upload so the snippets existed **only in S3**, exactly
like production (`upload_audio_snippet` stores the S3 key and deletes its temp).

## Acceptance criteria → evidence

| Criterion | Evidence |
|---|---|
| Composed episode actually contains intro → main → outro, verified by duration | Tones: intro 3.03s, main 5.04s, outro 4.05s → composed output **12.04s** (`ffprobe`), status `success` |
| Download failures degrade to main-only (log, don't fail the chain) | Timeline with a nonexistent S3 key → warning `Composition: skipping intro segment — download of s3://…/does-not-exist.mp3 failed: … 404 …`, status `success`, output **5.04s** (main only) |
| Temp snippet files cleaned up after merge (success and failure paths) | `$TMPDIR/tmp*.mp3` diff before/after both cases: **0 leaked files** (includes the pre-created tempfile of the failed download) |
| Unit tests for download/degrade/cleanup | `tests/unit/test_audio_composition_task.py::TestS3BackedSegments` (3 tests) + 3 resolver tests in `tests/unit/test_podcast_generation_task.py`; full suite 1828 passed / 7 skipped |

## Transcript

```text
Composition: skipping intro segment — download of s3://podcaststudiohub-audio/audio-snippets/demo-376/does-not-exist.mp3 failed: An error occurred (404) when calling the HeadObject operation: Not Found
tones: intro=3.03s main=5.04s outro=4.05s
uploaded snippets to s3://podcaststudiohub-audio/audio-snippets/demo-376/ and removed local copies
case1 composed: status=success duration=12.04s (expected ~12s)
case2 degraded: status=success duration=5.04s (expected ~5s)
tempfile cleanup: 0 leaked snippet tempfiles (expected 0)
demo S3 objects deleted — ALL CHECKS PASSED
```

Demo S3 objects were deleted at the end of the run.
