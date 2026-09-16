# Issue #501: S3 upload failures are 503 and never leak bucket/tenant detail

*2026-09-16T02:45:30Z*

The API is started locally on :8017 with `AWS_S3_BUCKET=psh-issue501-demo-bucket` and bogus AWS credentials, so every real PutObject against AWS fails. Before this fix the boto error text (bucket, key, tenant/episode UUIDs) was interpolated into a client-visible 422. The four acceptance criteria from the issue are each exercised below.

```bash
curl -s $API/health
```

```output
{"status":"healthy","version":"0.1.0"}```
```

**Setup** — register a user (the token is captured to a file and redacted here), then create a project and an episode for the PDF upload path.

```bash
curl -s -X POST $API/auth/register -H "Content-Type: application/json" -d "{\"email\":\"demo501-$(date +%s)@example.com\",\"password\":\"Demo501-Passw0rd!\",\"full_name\":\"Demo 501\"}" | tee $SCR/reg.json | jq "{token_type, has_token: (.access_token|length>0)}"
```

```output
{
  "token_type": "bearer",
  "has_token": true
}
```

```bash
curl -s -X POST $API/projects -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"name\":\"Demo 501\",\"podcast_metadata\":{}}" | tee $SCR/proj.json | jq "{id, name}"
```

```output
{
  "id": "a53c6a59-894c-41f6-8fc3-4602764c766c",
  "name": "Demo 501"
}
```

```bash
curl -s -X POST $API/episodes -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"project_id\":\"$PROJECT_ID\",\"episode_metadata\":{\"title\":\"Demo 501\"}}" | tee $SCR/ep.json | jq "{id, project_id}"
```

```output
{
  "id": "1270f23c-390a-47cd-964a-413b3e128505",
  "project_id": "a53c6a59-894c-41f6-8fc3-4602764c766c"
}
```

## Criterion 1 — a storage failure returns 503 with a fixed message
Both uploads pass every client-side check (extension, content type, size, magic bytes) and then hit the real, failing S3 upload.

```bash
curl -s -o $SCR/resp_audio.json -w "HTTP %{http_code}\n" -X POST $API/audio-snippets/upload -H "Authorization: Bearer $TOKEN" -F "file=@$SCR/intro.mp3;type=audio/mpeg" -F name=Intro -F snippet_type=intro; cat $SCR/resp_audio.json; echo
```

```output
HTTP 503
{"detail":"File storage is unavailable."}
```

```bash
curl -s -o $SCR/resp_pdf.json -w "HTTP %{http_code}\n" -X POST $API/episodes/$EPISODE_ID/content/upload -H "Authorization: Bearer $TOKEN" -F "file=@$SCR/doc.pdf;type=application/pdf" -F auto_extract=false; cat $SCR/resp_pdf.json; echo
```

```output
HTTP 503
{"detail":"File storage is unavailable."}
```

## Criterion 4 — no response body interpolates `str(e)`
The two bodies above are searched for the bucket name, the AWS key id, the word AccessDenied/InvalidAccessKeyId, and the tenant/episode UUID. Expected: zero matches in every body.

```bash
cd $SCR && grep -c -E "psh-issue501-demo-bucket|AKIAISSUE501|AccessDenied|InvalidAccessKeyId|S3UploadFailedError|$EPISODE_ID|An error occurred" resp_audio.json resp_pdf.json; echo "exit=$?  (1 = no matches)"
```

```output
resp_audio.json:0
resp_pdf.json:0
exit=1  (1 = no matches)
```

## Criterion 1 (second half) — the boto detail is in the server log only
The same bucket name that is absent from the response bodies appears in the JSON server log, on the `logger.exception` records emitted by the two upload sites, with the boto traceback attached.

```bash
grep "S3 upload failed" $APILOG | jq -r "[.logger, .level, .message] | @tsv"
```

```output
src.services.audio_snippet_service	ERROR	S3 upload failed for audio snippet 7fe449f2-18d6-4b44-b5a9-6fb164de0548
src.services.content_service	ERROR	S3 upload failed for PDF on episode 1270f23c-390a-47cd-964a-413b3e128505
```

```bash
grep "S3 upload failed" $APILOG | jq -r ".exception" | grep -o -E "psh-issue501-demo-bucket|InvalidAccessKeyId|S3UploadFailedError" | sort | uniq -c
```

```output
      4 InvalidAccessKeyId
      4 S3UploadFailedError
      2 psh-issue501-demo-bucket
```

## Criterion 2 — a genuine local fault still returns 422
The API process has already resolved and cached its temp directory (`TMPDIR`). Making it unwritable turns the temp-file write into an `OSError` **before** the S3 call, which is the 422 arm. The 422 body is fixed text: the filesystem path from the `OSError` is not echoed.

```bash
chmod 500 $DEMO_TMP && ls -ld $DEMO_TMP | cut -d" " -f1
```

```output
dr-x------
```

```bash
curl -s -o $SCR/resp_audio_422.json -w "HTTP %{http_code}\n" -X POST $API/audio-snippets/upload -H "Authorization: Bearer $TOKEN" -F "file=@$SCR/intro.mp3;type=audio/mpeg" -F name=Intro -F snippet_type=intro; cat $SCR/resp_audio_422.json; echo
```

```output
HTTP 422
{"detail":"Failed to process audio file."}
```

```bash
curl -s -o $SCR/resp_pdf_422.json -w "HTTP %{http_code}\n" -X POST $API/episodes/$EPISODE_ID/content/upload -H "Authorization: Bearer $TOKEN" -F "file=@$SCR/doc.pdf;type=application/pdf" -F auto_extract=false; cat $SCR/resp_pdf_422.json; echo
```

```output
HTTP 422
{"detail":"Failed to store PDF."}
```

```bash
cd $SCR && grep -c -E "demo-tmp|Permission denied|Errno" resp_audio_422.json resp_pdf_422.json; echo "exit=$?  (1 = temp path not leaked)"
```

```output
resp_audio_422.json:0
resp_pdf_422.json:0
exit=1  (1 = temp path not leaked)
```

## Criterion 3 — tests cover both arms at both sites
Four new tests (two per service) patch the module-scope upload helper with a failing `side_effect`; each was also confirmed to fail under mutation of the status code, the fixed message, the `except` arm, and the log call.

```bash
uv run pytest tests/test_audio_snippets.py tests/test_content.py -k "s3_failure or local_io_failure" -q --no-cov -p no:cacheprovider 2>&1 | grep -E "passed|failed"
```

```output
====================== 4 passed, 109 deselected in 0.96s =======================
```
