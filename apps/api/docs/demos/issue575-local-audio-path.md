# #575 — the no-S3 audio path refuses a non-UUID episode_id before touching disk

*2026-10-12T07:23:56Z by Showboat 0.6.1*
<!-- showboat-id: b204d35d-12c1-4edc-8cd5-8ec734559bff -->

Each run calls the real `_persist_local_audio` against a fresh temp directory: no mocks, a real copy, a real filesystem. `/tmp/demo_575.py` lists every file under the temp root before and after.

**Traversal-shaped id:** refused, nothing written, and the storage directory is not even created.

```bash
. /tmp/demo575env.sh && .venv/bin/python /tmp/demo_575.py '../../escaped' 2>&1 | grep -v '^{'
```

```output
episode_id = '../../escaped'
before: ['run/podcast.mp3']
refused: episode_id is not a valid UUID: '../../escaped'
after:  ['run/podcast.mp3']
storage dir created: False
```

```bash
. /tmp/demo575env.sh && .venv/bin/python /tmp/demo_575.py '/etc/cron.d/x' 2>&1 | grep -v '^{'
```

```output
episode_id = '/etc/cron.d/x'
before: ['run/podcast.mp3']
refused: episode_id is not a valid UUID: '/etc/cron.d/x'
after:  ['run/podcast.mp3']
storage dir created: False
```

**Newline-suffixed UUID** (the shared-validator gap found in review; built inside Python, since shell substitution strips a trailing newline): refused too.

```bash
. /tmp/demo575env.sh && .venv/bin/python /tmp/demo_575.py UUID+NL 2>&1 | grep -v '^{'
```

```output
episode_id = '550e8400-e29b-41d4-a716-446655440000\n'
before: ['run/podcast.mp3']
refused: episode_id is not a valid UUID: '550e8400-e29b-41d4-a716-446655440000\n'
after:  ['run/podcast.mp3']
storage dir created: False
```

**A real UUID** (what every live caller sends): persisted inside the storage root as before.

```bash
. /tmp/demo575env.sh && .venv/bin/python /tmp/demo_575.py UUID 2>&1 | grep -v '^{' | sed -E 's/[0-9a-f]{8}-[0-9a-f-]{27}/<uuid>/g'
```

```output
episode_id = '<uuid>'
before: ['run/podcast.mp3']
persisted -> storage/audio/episode-<uuid>.mp3
after:  ['run/podcast.mp3', 'storage/audio/episode-<uuid>.mp3']
storage dir created: True
```

| Criterion | Evidence | Status |
|---|---|---|
| Rejects a non-UUID episode_id before touching the filesystem | Traversal, absolute and newline-suffixed ids are refused; file tree unchanged; storage dir never created | VERIFIED |
| A test asserts nothing is written for a traversal-shaped id | `tests/unit/test_persist_local_audio.py` asserts the tree is unchanged and the storage dir does not exist; fails under both mutations (guard deleted, guard moved after `makedirs`) | VERIFIED |
| (guard) valid UUIDs still persist | Real UUID persisted to `storage/audio/episode-<uuid>.mp3` | VERIFIED |
