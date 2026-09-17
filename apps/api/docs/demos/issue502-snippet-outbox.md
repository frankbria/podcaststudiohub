# Issue #502: snippet deletion queues its S3 key in the storage deletion outbox

*2026-09-17T02:55:09Z*

`delete_audio_snippet` was the only service-layer delete path that called S3 directly inside a blind `try/except`: a failed `delete_file` left the DB row gone and the object orphaned forever, with nothing queued and nothing retried. It now writes a `StorageDeletionOutbox` row in the same transaction as the row delete and triggers the GC drain post-commit, exactly like episode and account deletion (#366). Review also caught that upload persisted a generated `s3_key` even when S3 was unconfigured and nothing was uploaded, which would have made the new path queue objects that never existed; that key is no longer stored. The API runs locally on :8018 with S3 unconfigured, and the drain is exercised in-process against the local Postgres. The four acceptance criteria from the issue are each exercised below.

```bash
curl -s $API/health
```

```output
{"status":"healthy","version":"0.1.0"}```
```

**Setup** — register a user (token captured to a file, redacted here) and upload a real 8-second MP3 as a snippet. With S3 unconfigured, nothing is uploaded, so the record carries no `s3_key` and a pseudo `file_path` (the upload's temp file is unlinked; there is never a local file to reclaim).

```bash
curl -s -X POST $API/auth/register -H "Content-Type: application/json" -d "{\"email\":\"demo502-$(date +%s)@example.com\",\"password\":\"Demo502-Passw0rd!\",\"full_name\":\"Demo 502\"}" | tee $SCR/reg.json | jq "{token_type, has_token: (.access_token|length>0)}"
```

```output
{
  "token_type": "bearer",
  "has_token": true
}
```

```bash
curl -s -X POST $API/audio-snippets/upload -H "Authorization: Bearer $TOKEN" -F "file=@$SCR/intro.mp3;type=audio/mpeg" -F name=Intro-A -F snippet_type=intro | tee $SCR/snipA.json | jq "{id, user_id, tenant_id, s3_key, s3_url, file_path, duration_seconds}"
```

```output
{
  "id": "a8c09d9a-b41b-4569-a7fd-86298f3fa9cd",
  "user_id": "7155ebf7-a3f7-42f4-be35-f8b62464b6ba",
  "tenant_id": "3781d79b-0169-4ef1-9c4b-979581def611",
  "s3_key": null,
  "s3_url": null,
  "file_path": "audio-snippets/a8c09d9a-b41b-4569-a7fd-86298f3fa9cd.mp3",
  "duration_seconds": 8.0
}
```

## Criterion 2 — the direct `delete_file` call and its blind catch are gone
The whole body of `delete_audio_snippet` after the docstring: one outbox `add` before the single `commit`, and the only remaining `except` guards the post-commit broker call (the row is already durable at that point). The diff against `main` shows what was removed.

```bash
awk "/^async def delete_audio_snippet/{f=1} f&&/^async def generate_download_url/{exit} f" src/services/audio_snippet_service.py | awk "c>=2{print} /^\t\"\"\"\$/{c++}" | grep -v "^\s*$"
```

```output
	s3_key = snippet.s3_key
	if s3_key:
		db.add(StorageDeletionOutbox(tenant_id=snippet.tenant_id, s3_key=s3_key))
	await db.delete(snippet)
	await db.commit()
	if s3_key:
		try:
			drain_storage_deletion_outbox.delay()
		except Exception:  # noqa: BLE001 — the outbox row is already committed, so a broker failure only delays collection — beat drains the same row on its next tick (#366)
			logger.warning("Failed to trigger storage deletion drain for snippet %s", snippet.id)
```

```bash
git diff origin/main -- src/services/audio_snippet_service.py | grep -E "^[-+][^-+]" | grep -E "delete_file|except Exception|StorageDeletionOutbox|StorageService|logging|s3_key = None"
```

```output
+from ..models.storage_deletion_outbox import StorageDeletionOutbox
+			s3_key = None
-			from ..services.storage_service import StorageService
-				storage = StorageService(bucket_name=bucket, region_name=settings.AWS_REGION)
-				await storage.delete_file(snippet.s3_key)
-		except Exception:  # noqa: BLE001 — the DB row is deleted either way, so a storage failure must not block the delete; it leaves an orphaned object, which is the lesser outcome
+		db.add(StorageDeletionOutbox(tenant_id=snippet.tenant_id, s3_key=s3_key))
+		except Exception:  # noqa: BLE001 — the outbox row is already committed, so a broker failure only delays collection — beat drains the same row on its next tick (#366)
```

**A snippet that was never uploaded queues nothing.** Deleting snippet A returns 204 and leaves no outbox row for this tenant — there is no object to reclaim, so the GC is not sent chasing one.

```bash
curl -s -o /dev/null -w "DELETE A: HTTP %{http_code}\n" -X DELETE $API/audio-snippets/$SNIPPET_A -H "Authorization: Bearer $TOKEN"; $PSQL -tA -c "select count(*) as outbox_rows_for_tenant from storage_deletion_outbox where tenant_id = '$TENANT_ID'"
```

```output
DELETE A: HTTP 204
0
```

## Criterion 1 — deletion enqueues an outbox row in the same transaction as the row delete
This environment has no bucket, so snippet B stands in for a real upload: after uploading it, its row is patched with the key and URL `_upload_to_s3` would have produced (the same values a configured-S3 upload stores). Before the delete there is no outbox row for that key.

```bash
curl -s -X POST $API/audio-snippets/upload -H "Authorization: Bearer $TOKEN" -F "file=@$SCR/intro.mp3;type=audio/mpeg" -F name=Intro-B -F snippet_type=intro | tee $SCR/snipB.json | jq -r .id
```

```output
88dd7c14-72df-4fe6-aaa7-2e88ecdd8c25
```

```bash
$PSQL -q -c "update audio_snippets set s3_key = '$S3_KEY', s3_url = 'https://demo-bucket.s3.amazonaws.com/$S3_KEY' where id = '$SNIPPET_B'"; curl -s $API/audio-snippets/$SNIPPET_B -H "Authorization: Bearer $TOKEN" | jq "{id, tenant_id, s3_key}"; $PSQL -tA -c "select count(*) as outbox_rows_for_key from storage_deletion_outbox where s3_key = '$S3_KEY'"
```

```output
{
  "id": "88dd7c14-72df-4fe6-aaa7-2e88ecdd8c25",
  "tenant_id": "3781d79b-0169-4ef1-9c4b-979581def611",
  "s3_key": "audio-snippets/7155ebf7-a3f7-42f4-be35-f8b62464b6ba/88dd7c14-72df-4fe6-aaa7-2e88ecdd8c25.mp3"
}
0
```

```bash
curl -s -o /dev/null -w "DELETE B: HTTP %{http_code}\n" -X DELETE $API/audio-snippets/$SNIPPET_B -H "Authorization: Bearer $TOKEN"; curl -s -o /dev/null -w "GET B after delete: HTTP %{http_code}\n" $API/audio-snippets/$SNIPPET_B -H "Authorization: Bearer $TOKEN"
```

```output
DELETE B: HTTP 204
GET B after delete: HTTP 404
```

After the delete: the snippet row is gone and exactly one outbox row exists for its key, carrying the snippet's tenant, a NULL `file_path` and zero attempts. Both writes rode the one `commit()` shown above.

```bash
$PSQL -c "select (select count(*) from audio_snippets where id = '$SNIPPET_B') as snippet_rows, tenant_id, s3_key, file_path, attempts, last_attempt_at from storage_deletion_outbox where s3_key = '$S3_KEY'"; echo "tenant_id from the upload response: $TENANT_ID"
```

```output
 snippet_rows |              tenant_id               |                                            s3_key                                            | file_path | attempts | last_attempt_at
--------------+--------------------------------------+----------------------------------------------------------------------------------------------+-----------+----------+-----------------
            0 | 3781d79b-0169-4ef1-9c4b-979581def611 | audio-snippets/7155ebf7-a3f7-42f4-be35-f8b62464b6ba/88dd7c14-72df-4fe6-aaa7-2e88ecdd8c25.mp3 |           |        0 |
(1 row)

tenant_id from the upload response: 3781d79b-0169-4ef1-9c4b-979581def611
```

## Criterion 4 — the GC drain picks up snippet keys
`drain_storage_deletion_outbox` is run in-process (the same code the Celery beat tick and the post-commit trigger execute). First against a bucket that does not exist with bogus credentials: the drain claims the row, the real `DeleteObject` fails, and the row stays queued with `attempts` incremented — the retry-until-gone behaviour the outbox exists for.

```bash
AWS_S3_BUCKET=psh-issue502-demo-bucket AWS_ACCESS_KEY_ID=AKIAIOSFODNN7DEMO AWS_SECRET_ACCESS_KEY=demo-secret-not-real uv run --no-sync python -c "
import logging; logging.basicConfig(level=logging.WARNING, format=\"%(levelname)s %(name)s: %(message)s\")
from src.tasks.maintenance import drain_storage_deletion_outbox
print(\"drained:\", drain_storage_deletion_outbox())" 2>&1 | grep -E "drained:|$S3_KEY" | cut -c1-220
```

```output
WARNING src.tasks.maintenance: Failed to delete S3 object audio-snippets/7155ebf7-a3f7-42f4-be35-f8b62464b6ba/88dd7c14-72df-4fe6-aaa7-2e88ecdd8c25.mp3 (attempt 1): Failed to delete file from S3: An error occurred (Invali
drained: 0
```

```bash
$PSQL -c "select s3_key, attempts, last_attempt_at is not null as retried from storage_deletion_outbox where s3_key = '$S3_KEY'"
```

```output
                                            s3_key                                            | attempts | retried
----------------------------------------------------------------------------------------------+----------+---------
 audio-snippets/7155ebf7-a3f7-42f4-be35-f8b62464b6ba/88dd7c14-72df-4fe6-aaa7-2e88ecdd8c25.mp3 |        1 | t
(1 row)

```

Then with the storage call stubbed to succeed (nothing real to delete here): the drain hands the snippet key to `delete_file` and removes the row once the object is reported gone.

```bash
uv run --no-sync python -c "
from unittest.mock import patch, AsyncMock
from src.tasks.maintenance import drain_storage_deletion_outbox
with patch(\"src.tasks.maintenance.StorageService\") as svc:
    svc.return_value.delete_file = AsyncMock(return_value=None)
    print(\"drained:\", drain_storage_deletion_outbox())
    print(\"delete_file called with:\", [c.args[0] for c in svc.return_value.delete_file.await_args_list if c.args[0] == \"$S3_KEY\"])" 2>&1 | tail -2
```

```output
drained: 1
delete_file called with: ['audio-snippets/7155ebf7-a3f7-42f4-be35-f8b62464b6ba/88dd7c14-72df-4fe6-aaa7-2e88ecdd8c25.mp3']
```

```bash
$PSQL -tA -c "select count(*) as outbox_rows_for_key from storage_deletion_outbox where s3_key = '$S3_KEY'"
```

```output
0
```

## Criterion 3 — a test asserts the outbox row is created
Four new tests: the S3-key case asserts the row (tenant, NULL `file_path`), that no synchronous `delete_file` happens and that the drain is triggered; the no-key case asserts no row and no drain; the broker-down case asserts the delete still succeeds and the committed row survives; and the upload case asserts no phantom key is stored when S3 is unconfigured. Then the enqueue line is removed live and the first test fails on the missing row, proving it asserts the behaviour rather than the import path.

```bash
uv run --no-sync pytest tests/test_audio_snippets.py -k "outbox or drain_delay or without_s3" -q -p no:cacheprovider --no-cov 2>&1 | grep -E "passed|failed"
```

```output
======================= 4 passed, 54 deselected in 1.03s =======================
```

```bash
sed -i "s/^\t\tdb.add(StorageDeletionOutbox(tenant_id=snippet.tenant_id, s3_key=s3_key))$/\t\tpass/" src/services/audio_snippet_service.py; uv run --no-sync pytest tests/test_audio_snippets.py -k with_s3_key_queues_outbox_row -q -p no:cacheprovider --no-cov 2>&1 | grep -E "NoResultFound|passed|failed" | tail -2; git checkout -- src/services/audio_snippet_service.py; echo "restored: $(git status --short src/ | wc -l) modified files under src/"
```

```output
.venv/lib/python3.12/site-packages/sqlalchemy/engine/result.py:799: NoResultFound
======================= 1 failed, 57 deselected in 0.43s =======================
restored: 0 modified files under src/
```
