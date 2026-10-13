# #626 — the public audio URL refuses audio held for review

*2026-10-13T01:36:21Z by Showboat 0.6.1*
<!-- showboat-id: 3b0cd2e2-24bb-4ad3-9934-fa6770572634 -->

Closes the gap #576 left open (owner-accepted, M2 in its review): a regeneration overwrites the canonical audio key, so the unauthenticated `/feeds/episodes/{user}/{episode}/audio.mp3` served newly flagged audio before approval. The upload now marks held audio with S3 object metadata `content-review: pending`; the public endpoint (which by design reads no database, #385) refuses marked objects; approval clears the mark in place before recording `approved`.

Run on the **real** database and a **real** S3 API: a throwaway SeaweedFS S3 container (`docker run -d --rm --name demo626-s3 -p 127.0.0.1:59000:8333 chrislusf/seaweedfs:4.48 server -s3 -dir=/data`), reached through boto3's standard `AWS_ENDPOINT_URL`. No application code knows about it. The real `upload_to_s3_task`, the real FastAPI route over ASGI, and the real `approve_content_review` run; the 302 is followed to the object store. The only stub is the feed rebuild dispatch. Driver: `/tmp/demo_626.py`, env `/tmp/demo626_env.sh`.

Running it surfaced a latent bug, fixed here: s3transfer calls the progress `Callback` on its own threads, where Celery's thread-local `self.request.id` is `None`, so `update_state` raised and **every real upload failed**. Unit tests mocked `upload_file` and never ran the callback on a transfer thread; a test now does.

```bash
. /tmp/demo626_env.sh && .venv/bin/python /tmp/demo_626.py 2>&1 | grep -vE "^\s*$|WARNING|DEBUG"
```

```output
upload, held episode  -> metadata, type: ({'content-review': 'pending'}, 'audio/mpeg')
upload, clean episode -> metadata, type: ({}, 'audio/mpeg')
public audio, held : (404, None)
public audio, clean: (302, (200, 'audio/mpeg', b'ID3f'))
after approve -> metadata, type: ({}, 'audio/mpeg')
public audio, held after approve: (302, (200, 'audio/mpeg', b'ID3f'))
public audio, never uploaded: 404
```

Held audio uploads marked and the public URL answers 404, the same as a missing object, so it reveals nothing. Clean audio carries no mark and serves. Approval drops the mark, keeps `audio/mpeg` (a `MetadataDirective=REPLACE` copy would otherwise reset it), and the same URL then serves the object.
