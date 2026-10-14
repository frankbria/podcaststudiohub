# #629 — a redelivered upload cannot leave approved audio marked as held

*2026-10-14T03:22:52Z by Showboat 0.6.1*
<!-- showboat-id: c1101b56-85be-47dd-8f3d-91dad94b6497 -->

Against the real database, with only boto3 faked. The first test commits an approval between the upload's hold read and its object write: the marked object is then replaced by an unmarked one. The third holds approval's FOR UPDATE open and shows the upload's re-check blocks until it commits, then reads 'not held'.

```bash
. /home/frankbria/.claude/jobs/a14abad9/tmp/testenv.sh && $PY -m pytest tests/test_held_audio_upload.py --no-cov -p no:cacheprovider -q -k 'approval or still_held or recheck' -v 2>&1 | grep -E 'PASSED|FAILED' | sed 's/ *\[.*//'
```

```output
tests/test_held_audio_upload.py::test_an_approval_between_the_hold_read_and_the_object_write_leaves_no_mark PASSED
tests/test_held_audio_upload.py::test_a_still_held_episode_is_written_once_and_stays_marked PASSED
tests/test_held_audio_upload.py::test_the_recheck_waits_for_an_approval_that_has_not_committed_yet PASSED
```

The whole upload / review net:

```bash
. /home/frankbria/.claude/jobs/a14abad9/tmp/testenv.sh && $PY -m pytest tests/test_held_audio_upload.py tests/test_s3_upload.py tests/unit/test_task_retry.py tests/unit/test_storage_review_hold.py tests/test_episodes.py --no-cov -p no:cacheprovider -q 2>&1 | tail -1 | sed 's/ in .*//'
```

```output
======================= 165 passed, 1 skipped
```
