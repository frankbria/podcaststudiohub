"""
Contract tests for tests.module_patching.patch_modules (issue #372).

Deterministically guards the fix regardless of collection order:
tests/test_sync_jsonb_isolation.py is the full-suite canary; these tests
pin the helper's restore semantics directly.
"""
import sys
import types

from tests.module_patching import patch_modules


def test_module_imported_inside_window_survives_exit():
    # The #372 bug: patch.dict(sys.modules, ...) evicted modules imported
    # during the window (psycopg tree). patch_modules must not.
    probe = "xml.sax.saxutils"
    sys.modules.pop(probe, None)
    with patch_modules({"fake_pkg_372": types.ModuleType("fake_pkg_372")}):
        import xml.sax.saxutils  # noqa: F401
        assert probe in sys.modules
    assert probe in sys.modules


def test_patched_key_absent_before_is_removed_after():
    fake = types.ModuleType("fake_pkg_372")
    with patch_modules({"fake_pkg_372": fake}):
        assert sys.modules["fake_pkg_372"] is fake
    assert "fake_pkg_372" not in sys.modules


def test_patched_key_present_before_is_restored_after():
    original = sys.modules["uuid"]
    with patch_modules({"uuid": types.ModuleType("uuid")}):
        assert sys.modules["uuid"] is not original
    assert sys.modules["uuid"] is original


def test_keys_restored_when_body_raises():
    original = sys.modules["uuid"]
    try:
        with patch_modules({"uuid": types.ModuleType("uuid"), "fake_pkg_372": types.ModuleType("f")}):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert sys.modules["uuid"] is original
    assert "fake_pkg_372" not in sys.modules
