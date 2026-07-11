"""
Scoped sys.modules patching for tests (issue #372).

Never use ``unittest.mock.patch.dict(sys.modules, {...})``: its exit path
clears the dict and re-applies a snapshot, evicting every module imported
during the window. Evicting C-extension-backed packages (psycopg) breaks
their global adapter state for the rest of the pytest session — see #372.

``patch_modules`` restores only the keys it patched.
"""
import sys
from contextlib import contextmanager

_MISSING = object()


@contextmanager
def patch_modules(mapping):
    """Temporarily set sys.modules entries; on exit restore only those keys."""
    saved = {name: sys.modules.get(name, _MISSING) for name in mapping}
    sys.modules.update(mapping)
    try:
        yield
    finally:
        for name, original in saved.items():
            if original is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
