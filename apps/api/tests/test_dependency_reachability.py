"""The old engine's dependency tree stays gone (#446, #518, #543).

podcastfy capped the whole langchain/litellm tree, which is why
``scripts/pip_audit_gate.py`` once let ~30 advisories through and why the
original version of this file proved their code unreachable. #543 removed
podcastfy, so that proof is replaced by something stronger: the packages are
not installed at all, and the in-repo engine may not bring them back.

The previous analysis is kept as history in
apps/api/docs/podcastfy-advisory-reachability.md.
"""

import re
import subprocess
import sys
import textwrap


def _run_probe(source: str) -> str:
    """Run an import probe in a clean interpreter.

    A subprocess is required, not stylistic: `sys.modules` is process-global, so any
    earlier test that imported litellm would make an in-process assertion pass or
    fail based on test ordering rather than on our actual import graph.
    """
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        capture_output=True,
        text=True,
        timeout=600,
        # The assert below checks returncode and reports stdout/stderr, which is
        # a far better failure message than CalledProcessError would give.
        check=False,
    )
    assert result.returncode == 0, (
        f"probe failed (exit {result.returncode})\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    return result.stdout


# The packages podcastfy pulled in that carried the advisories, plus podcastfy
# itself. Any of these reappearing (a stray dependency, a transitive pin) would
# silently re-open the advisory surface the removal closed.
_REMOVED_TREE = (
    "podcastfy",
    "langchain",
    "langchain_core",
    "langchain_community",
    "langsmith",
    "litellm",
)


def test_the_old_engines_dependency_tree_is_not_installed():
    out = _run_probe(
        f"""
        import importlib.util
        for name in {_REMOVED_TREE!r}:
            print(name, importlib.util.find_spec(name) is not None)
        """
    )
    installed = [line.split()[0] for line in out.splitlines() if line.endswith("True")]
    assert not installed, (
        f"{installed} installed again; the advisory surface #543 removed is back. "
        "Find the dependency that pulls it in (uv tree --invert --package <name>)."
    )


def test_engine_package_never_imports_langchain_or_litellm():
    """The in-repo engine (#541) exists to get off that tree, not to re-enter it.

    podcastfy reached litellm/langchain through `content_generator.py` — the single
    file that carried the whole 31-entry suppression list and the `openai<2` ceiling
    (#518), plus the LangChain Hub fetch on every paid generation (#446). `src/engine`
    calls the provider SDKs directly. If an import creeps back, the closure that #543
    is meant to delete becomes load-bearing again.
    """
    from pathlib import Path

    engine = Path(__file__).resolve().parents[1] / "src" / "engine"
    scanned = list(engine.rglob("*.py"))
    # Without this the test passes vacuously if the package is renamed or moved.
    assert len(scanned) >= 5, (
        f"expected to scan the engine package, found {len(scanned)} files under "
        f"{engine} — has the layout changed?"
    )

    # Matched against import statements and the hub call specifically, not any
    # mention: these modules' docstrings explain what they exist to avoid, and a
    # bare substring scan would flag that prose. The blunt substring check still
    # exists one test up (test_no_caller_selects_a_non_default_llm), applied to
    # all of src/ including this package.
    banned = re.compile(
        r"^\s*(?:from|import)\s+[\w.]*\b(?:langchain\w*|langsmith)\b|\bhub\.pull\s*\("
    )
    offenders = [
        f"{path.relative_to(engine)}:{i}: {line.strip()}"
        for path in scanned
        for i, line in enumerate(path.read_text().splitlines(), 1)
        if banned.search(line)
    ]
    assert not offenders, (
        "src/engine now references the langchain/litellm tree the engine was built "
        "to replace. Call the provider SDK directly instead; if this is deliberate, "
        "scripts/pip_audit_gate.py and docs/podcastfy-advisory-reachability.md both "
        f"need revisiting first: {offenders}"
    )


def test_importing_the_engine_pulls_in_neither_langchain_nor_litellm():
    """Source-level grep's runtime counterpart: a transitive import counts too.

    A helper that looks clean can still drag the tree in through what it imports,
    so this asserts on the actual module graph after importing the engine.
    """
    from pathlib import Path

    api_root = Path(__file__).resolve().parents[1]
    printed = _run_probe(
        f"""
        import os, sys
        sys.path.insert(0, {str(api_root)!r})
        # src.config instantiates Settings at import time; these only need to be
        # present and well-formed, they are never used to connect to anything.
        os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
        os.environ.setdefault("ENCRYPTION_KEY", "x" * 32)
        os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)

        import src.engine  # noqa: F401
        from src.engine import ConversationConfig, generate_script

        # Importing is not enough: a lazy `import langchain_community` inside a
        # provider function would load only when that function runs, i.e. after
        # an import-only snapshot was taken. So drive the real call path with a
        # stand-in client, exactly as the litellm probe above constructs a real
        # ContentGenerator rather than just importing one.
        import json
        from unittest.mock import MagicMock, patch

        from google.genai import types

        reply = types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(parts=[
                types.Part(text=json.dumps({{
                    "title": "t", "summary": "s",
                    "turns": [
                        {{"speaker": "host", "text": "word " * 60}},
                        {{"speaker": "guest", "text": "word " * 60}},
                        {{"speaker": "host", "text": "word " * 60}},
                        {{"speaker": "guest", "text": "word " * 60}},
                    ],
                }}))
            ]))]
        )
        client = MagicMock()
        client.models.generate_content.return_value = reply

        from src.config import settings as _settings
        with patch("src.engine.llm.genai.Client", return_value=client), \
                patch.object(_settings, "GEMINI_API_KEY", "probe-key"), \
                patch.object(_settings, "ENGINE_LLM_PROVIDER", "gemini"):
            script = generate_script(["Body text to discuss."], ConversationConfig())
        assert len(script.turns) == 4, script

        found = sorted(
            {{m.split(".")[0] for m in sys.modules
              if m.split(".")[0] in ("langchain", "litellm", "langsmith")}}
        )
        print("ENGINE_TREE=" + (",".join(found) or "NONE"))
        """
    )
    assert "ENGINE_TREE=NONE" in printed, (
        "Importing src.engine dragged in the langchain/litellm tree transitively: "
        f"{printed.strip()}"
    )
