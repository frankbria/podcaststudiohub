# Issue #519: a failed stage records its own name

*2026-09-18T16:31:26Z*

A real Celery worker (Redis broker, local Postgres) runs a generation chain whose composition stage fails deterministically, because an empty timeline makes merge_audio_snippets raise ValueError. We read generation_progress.failed_task back from the DB twice. The first run re-adds the chain-level errback that #519 removes, which is main's behaviour. The second run uses the branch unchanged. The worker also consumes the default celery queue, because merge_audio_snippets is registered under a bare name that no task_routes pattern matches.

```bash
mkdir -p /tmp/demo519 && cat > /tmp/demo519/driver.py <<'PY'
"""Run one real generation chain whose composition stage fails; print failed_task.

argv[1] == "main-behaviour" re-adds the chain-level errback removed in #519.
"""
import sys
import time
import uuid

from src.database import SyncSessionLocal
from src.models.episode import Episode
from src.models.project import Project
from src.models.user import User
from src.tasks.callbacks import on_workflow_failure
from src.tasks.podcast_generation import build_generation_workflow

mode = sys.argv[1]
tenant = uuid.uuid4()
with SyncSessionLocal() as db:
	user = User(email=f"demo519-{uuid.uuid4().hex[:8]}@example.com", password_hash="x", tenant_id=tenant)
	db.add(user)
	db.flush()
	project = Project(user_id=user.id, tenant_id=tenant, name="demo 519")
	db.add(project)
	db.flush()
	ep = Episode(
		user_id=user.id, project_id=project.id, tenant_id=tenant,
		episode_number=1, generation_status="generating",
	)
	db.add(ep)
	db.commit()
	user_id, episode_id = str(user.id), str(ep.id)

try:
	workflow = build_generation_workflow(
		episode_id=episode_id,
		audio_file_path="/tmp/demo519.mp3",
		user_id=user_id,
		s3_bucket="demo-bucket",
		enable_composition=True,
		composition_timeline=[],  # empty timeline -> merge_audio_snippets raises ValueError
	)
	if mode == "main-behaviour":
		workflow.link_error(on_workflow_failure.s(episode_id=episode_id, task_name="workflow"))
	workflow.apply_async()

	deadline = time.time() + 60
	while time.time() < deadline:
		with SyncSessionLocal() as db:
			if db.get(Episode, uuid.UUID(episode_id)).generation_status == "failed":
				break
		time.sleep(0.5)
	time.sleep(5)  # let any second errback land
	with SyncSessionLocal() as db:
		ep = db.get(Episode, uuid.UUID(episode_id))
		print(f"mode={mode}")
		print(f"generation_status={ep.generation_status}")
		print(f"failed_task={ep.generation_progress.get('failed_task')}")
		print("error_message=" + ep.generation_progress.get("error_message", "").split(" for episode")[0])
finally:
	with SyncSessionLocal() as db:
		db.delete(db.get(User, uuid.UUID(user_id)))
		db.commit()
PY
echo driver written: $(wc -l < /tmp/demo519/driver.py) lines
```

```output
driver written: 62 lines
```

```bash
(uv run --no-sync celery -A src.worker:celery_app worker -Q celery,audio_processing,callbacks -P solo -l info > /tmp/demo519/worker.log 2>&1 &); for i in $(seq 1 40); do grep -q 'ready' /tmp/demo519/worker.log && break; sleep 1; done; grep -c 'ready' /tmp/demo519/worker.log
```

```output
1
```

Before (main's behaviour: the chain-level link_error is present). A second, generic errback overwrites the stage name:

```bash
PYTHONPATH=. uv run --no-sync python /tmp/demo519/driver.py main-behaviour 2>&1 | grep -v '^{'; echo on_workflow_failure deliveries: $(grep -o 'Task on_workflow_failure\[[^]]*\] received' /tmp/demo519/worker.log | wc -l)
```

```output
mode=main-behaviour
generation_status=failed
failed_task=workflow
error_message=Task 'workflow' failed: Composition timeline
on_workflow_failure deliveries: 2
```

After (this branch). One errback per stage, and failed_task names the stage that failed:

```bash
PYTHONPATH=. uv run --no-sync python /tmp/demo519/driver.py branch 2>&1 | grep -v '^{'; echo on_workflow_failure deliveries so far: $(grep -o 'Task on_workflow_failure\[[^]]*\] received' /tmp/demo519/worker.log | wc -l)
```

```output
mode=branch
generation_status=failed
failed_task=merge_audio_snippets
error_message=Task 'merge_audio_snippets' failed: Composition timeline
on_workflow_failure deliveries so far: 3
```

```bash
ps -eo pid,args | grep '[c]elery -A src.worker' | awk '{print $1}' | xargs -r kill; sleep 2; echo worker stopped
```

```output
worker stopped
```
