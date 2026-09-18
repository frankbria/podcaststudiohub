"""The pip-audit gate's classification rules (#518).

Runs scripts/pip_audit_gate.py as CI does — a subprocess over a pip-audit JSON report —
so the exit code, the annotations and the step summary are what's under test.
"""

import json
import subprocess
import sys
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / "scripts" / "pip_audit_gate.py"


def _vuln(vid, aliases=()):
    return {
        "id": vid,
        "fix_versions": ["9.9.9"],
        "aliases": list(aliases),
        "description": "x",
    }


def _run(tmp_path, dependencies, *, raw=None):
    report = tmp_path / "audit.json"
    report.write_text(
        raw if raw is not None else json.dumps({"dependencies": dependencies})
    )
    summary = tmp_path / "summary.md"
    result = subprocess.run(
        [sys.executable, str(GATE), str(report)],
        capture_output=True,
        text=True,
        env={"GITHUB_STEP_SUMMARY": str(summary)},
        check=False,
    )
    return result, summary.read_text() if summary.exists() else ""


def test_new_litellm_advisory_warns_but_does_not_block(tmp_path):
    result, summary = _run(
        tmp_path,
        [
            {
                "name": "litellm",
                "version": "1.80.0",
                "vulns": [_vuln("CVE-2099-0001", ["GHSA-aaaa"])] * 2,
            }
        ],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("::warning") == 1 and "CVE-2099-0001" in result.stdout
    assert summary.count("CVE-2099-0001") == 1  # pip-audit's duplicate records collapse


def test_unlisted_advisory_in_any_other_package_fails_loudly(tmp_path):
    result, summary = _run(
        tmp_path,
        [
            {"name": "litellm", "version": "1.80.0", "vulns": [_vuln("CVE-2099-0001")]},
            {"name": "requests", "version": "2.0.0", "vulns": [_vuln("CVE-2099-0002")]},
        ],
    )
    assert result.returncode == 1
    assert "::error" in result.stdout and "requests" in result.stdout
    assert "CVE-2099-0002" in result.stdout
    assert "CVE-2099-0002" in summary


def test_triaged_non_litellm_advisory_is_ignored_by_id_or_alias(tmp_path):
    result, _ = _run(
        tmp_path,
        [
            # listed by its primary id
            {"name": "pytest", "version": "8.4.2", "vulns": [_vuln("PYSEC-2026-1845")]},
            # listed by an alias (pip-audit reports PYSEC-2026-2192, we list the CVE)
            {
                "name": "langchain",
                "version": "0.3.0",
                "vulns": [_vuln("PYSEC-2026-2192", ["CVE-2026-55443"])],
            },
        ],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "::error" not in result.stdout


def test_clean_report_passes(tmp_path):
    result, _ = _run(tmp_path, [{"name": "fastapi", "version": "1.0", "vulns": []}])
    assert result.returncode == 0, result.stdout + result.stderr


def test_unparseable_report_fails_closed(tmp_path):
    result, _ = _run(tmp_path, None, raw="pip-audit crashed before writing JSON")
    assert result.returncode == 1


def test_skipped_dependency_fails_closed(tmp_path):
    result, _ = _run(
        tmp_path, [{"name": "mystery", "skip_reason": "could not resolve"}]
    )
    assert result.returncode == 1
    assert "mystery" in result.stdout
