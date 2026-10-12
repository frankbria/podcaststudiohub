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


def test_a_litellm_advisory_blocks_now_that_the_allowance_is_gone(tmp_path):
    """litellm was warn-only only because podcastfy capped it (#518); since #543
    it is not installed, so an advisory for it is a real finding again."""
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
    assert result.returncode == 1
    assert result.stdout.count("::error") == 1 and "CVE-2099-0001" in result.stdout
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


def test_formerly_triaged_ids_block_again(tmp_path):
    """The ten podcastfy-era TRIAGED ids are gone with podcastfy (#543)."""
    result, _ = _run(
        tmp_path,
        [{"name": "pytest", "version": "8.4.2", "vulns": [_vuln("PYSEC-2026-1845")]}],
    )
    assert result.returncode == 1
    assert "PYSEC-2026-1845" in result.stdout


def test_the_allowlist_mechanism_still_works_if_an_entry_is_ever_added(tmp_path, monkeypatch):
    """Both lists are empty, but the mechanism stays: exercised in-process with
    the sets patched, by id and by alias, warn-only and triaged."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("pip_audit_gate", GATE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    monkeypatch.setattr(gate, "TRIAGED", {"CVE-2026-55443"})
    monkeypatch.setattr(gate, "WARN_ONLY_PACKAGES", {"somepkg"})
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    report = tmp_path / "audit.json"
    report.write_text(json.dumps({"dependencies": [
        # triaged by alias: pip-audit reports PYSEC-2026-2192, the list holds the CVE
        {"name": "a", "version": "1", "vulns": [_vuln("PYSEC-2026-2192", ["CVE-2026-55443"])]},
        {"name": "somepkg", "version": "1", "vulns": [_vuln("CVE-2099-0003")]},
    ]}))

    assert gate.main(str(report)) == 0


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


def test_annotation_properties_carry_no_bare_comma(tmp_path):
    """GitHub splits `::cmd k=v,k=v::` properties on a bare comma — one in a title truncates it."""
    result, _ = _run(
        tmp_path,
        [
            {"name": "litellm", "version": "1.80.0", "vulns": [_vuln("CVE-2099-0001")]},
            {"name": "requests", "version": "2.0.0", "vulns": [_vuln("CVE-2099-0002")]},
        ],
    )
    commands = [line for line in result.stdout.splitlines() if line.startswith("::")]
    assert len(commands) == 2
    for line in commands:
        properties = line[2:].split("::", 1)[0]
        assert "," not in properties, line
