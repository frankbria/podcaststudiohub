# #527 — an exhausted content-source task marks the source failed

*2026-10-13T21:41:46Z by Showboat 0.6.1*
<!-- showboat-id: 76f2a8d8-9c10-4d3a-bc9d-eba52ce17869 -->

Real database rows, Celery's real retry decision (`push_request(retries=max_retries)`, no retry mock); only the unclassified error is injected. The polling endpoint (`GET /content-sources/{id}/status`, `get_extraction_status` in `routers/content.py`) returns `extraction_status` and `error_message` straight from the row, so what the test reads is what the UI shows. On `main` all three fail: the row stays `extracting`.

```bash
. /tmp/claude-1002/-home-frankbria-projects-podcaststudiohub/0cff25cd-5ade-4521-b4a7-6a902107273a/scratchpad/testenv.sh && .venv/bin/python -m pytest tests/test_content_source_terminal_status.py -v --no-cov -p no:cacheprovider 2>&1 | grep -E "PASSED|FAILED|passed|failed"
```

```output
tests/test_content_source_terminal_status.py::test_exhausted_retries_mark_the_source_failed_and_still_fail_the_task[extract_content_task-extra0] PASSED [ 33%]
tests/test_content_source_terminal_status.py::test_exhausted_retries_mark_the_source_failed_and_still_fail_the_task[validate_url_reachability_task-extra1] PASSED [ 66%]
tests/test_content_source_terminal_status.py::test_a_failed_status_write_never_hides_the_original_error PASSED [100%]
0.24s teardown tests/test_content_source_terminal_status.py::test_exhausted_retries_mark_the_source_failed_and_still_fail_the_task[extract_content_task-extra0]
0.18s call     tests/test_content_source_terminal_status.py::test_exhausted_retries_mark_the_source_failed_and_still_fail_the_task[extract_content_task-extra0]
0.17s setup    tests/test_content_source_terminal_status.py::test_exhausted_retries_mark_the_source_failed_and_still_fail_the_task[extract_content_task-extra0]
0.04s setup    tests/test_content_source_terminal_status.py::test_exhausted_retries_mark_the_source_failed_and_still_fail_the_task[validate_url_reachability_task-extra1]
0.04s setup    tests/test_content_source_terminal_status.py::test_a_failed_status_write_never_hides_the_original_error
0.04s teardown tests/test_content_source_terminal_status.py::test_exhausted_retries_mark_the_source_failed_and_still_fail_the_task[validate_url_reachability_task-extra1]
0.04s teardown tests/test_content_source_terminal_status.py::test_a_failed_status_write_never_hides_the_original_error
0.03s call     tests/test_content_source_terminal_status.py::test_exhausted_retries_mark_the_source_failed_and_still_fail_the_task[validate_url_reachability_task-extra1]
0.01s call     tests/test_content_source_terminal_status.py::test_a_failed_status_write_never_hides_the_original_error
============================== 3 passed in 0.82s ===============================
```
