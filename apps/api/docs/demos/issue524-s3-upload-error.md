# #524 — upload_file catches the error boto3 really raises

*2026-10-13T21:29:12Z by Showboat 0.6.1*
<!-- showboat-id: 6dd5c211-3510-474a-a4b1-753870d0f822 -->

boto3's `upload_file` (S3Transfer) wraps the S3 `ClientError` in `S3UploadFailedError`, so `StorageService.upload_file`'s `except ClientError` never ran in production. The test below uses a **real** boto3 client whose `PutObject` is answered `403 InvalidAccessKeyId` at the last hook before the wire, so boto3's own transfer layer produces the exception. On `main` the same test failed with `Actual message: 'Failed to upload /tmp/.../test.mp3 to bucket/key.mp3: An error occurred (InvalidAccessKeyId) ...'`: the raw `S3UploadFailedError`, never the wrapper.

```bash
. /tmp/claude-1002/-home-frankbria-projects-podcaststudiohub/0cff25cd-5ade-4521-b4a7-6a902107273a/scratchpad/testenv.sh && .venv/bin/python -m pytest tests/unit/test_storage_service.py -k actually_raises -v --no-cov -p no:cacheprovider 2>&1 | grep -E "PASSED|FAILED|passed|failed"
```

```output
tests/unit/test_storage_service.py::test_upload_file_wraps_the_error_boto3_actually_raises PASSED [100%]
======================= 1 passed, 19 deselected in 0.12s =======================
```
