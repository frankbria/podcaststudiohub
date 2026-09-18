"""Reachability guards for advisories in the podcastfy dependency closure (#446).

`scripts/pip_audit_gate.py` lets through advisories that no bump can clear, because
`podcastfy==0.4.1` caps the whole langchain/litellm tree: all litellm advisories (as
non-blocking warnings) and an enumerated list of the rest. Letting them through is only
defensible while the vulnerable code is genuinely unreachable from our call paths.

That "unreachable" claim is a property of the import graph and the API surface, both
of which drift. These tests turn it into an enforced invariant: if a future change
makes the vulnerable code reachable, the ignore list becomes a lie and CI says so.

See apps/api/docs/podcastfy-advisory-reachability.md for the full classification.
"""

import subprocess
import sys
import textwrap
from typing import get_args


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


def test_litellm_is_never_imported_by_the_generation_stack():
    """The compensating control for every litellm advisory (#446, #518).

    scripts/pip_audit_gate.py reports litellm advisories without blocking, because
    litellm is capped by podcastfy and never runs here. That is only true while this
    test is green: podcastfy reaches litellm solely through langchain_community's
    ChatLiteLLM, which imports it lazily and is only built for a non-gemini model.

    So the probe goes past import and builds the LLM backend exactly as podcastfy's
    process_content does for our call (model_name=None -> config's gemini model ->
    ChatGoogleGenerativeAI). If any litellm module — proxy or core — loads, the
    advisories are no longer inert and this fails.
    """
    output = _run_probe(
        """
        import os, sys, tempfile
        os.environ.setdefault("GEMINI_API_KEY", "probe-not-a-real-key")
        os.chdir(tempfile.mkdtemp())  # ContentGenerator creates ./data/transcripts

        # The real generation entry points used by src/tasks/podcast_generation.py
        from podcastfy.client import generate_podcast          # noqa: F401
        from podcastfy.content_generator import ContentGenerator
        from podcastfy.utils.config_conversation import load_conversation_config

        # Mirrors podcastfy.client.process_content: we never pass a model name.
        ContentGenerator(
            is_local=False,
            model_name=None,
            api_key_label=None,
            conversation_config=load_conversation_config().to_dict(),
        )

        loaded = sorted(
            m for m in sys.modules if m == "litellm" or m.startswith("litellm.")
        )
        print("LITELLM_MODULES=" + (",".join(loaded) if loaded else "NONE"))
        """
    )
    assert "LITELLM_MODULES=NONE" in output, (
        "litellm now loads with the generation stack. scripts/pip_audit_gate.py "
        "treats litellm advisories as non-blocking on the premise that it never "
        "runs — that premise is gone. Move litellm out of WARN_ONLY_PACKAGES and "
        f"triage its advisories. Probe output: {output!r}"
    )


def test_no_caller_selects_a_non_default_llm():
    """Second half of the guard above: a model name routes podcastfy to ChatLiteLLM.

    LLMBackend builds ChatLiteLLM for any non-gemini model_name. We never pass one
    (`llm_model_name` to generate_podcast), and nothing of ours imports litellm.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src"
    scanned = list(src.rglob("*.py"))
    assert len(scanned) > 50, f"expected to scan {src}, found {len(scanned)} files"

    offenders = [
        f"{path.relative_to(src)}:{i}"
        for path in scanned
        for i, line in enumerate(path.read_text().splitlines(), 1)
        if "llm_model_name" in line or "litellm" in line.lower()
    ]
    assert not offenders, (
        "Our source now selects an LLM model or touches litellm directly, which can "
        "make litellm reachable (see scripts/pip_audit_gate.py): " + str(offenders)
    )


def test_no_image_source_type_keeps_the_image_url_path_unreachable():
    """GHSA-2g6r (SSRF via image_url token counting) needs image input.

    podcastfy builds `image_url` message parts (content_generator.py:805) only when
    `image_paths` is non-empty. `generate_podcast_task` accepts that kwarg but no
    caller populates it, because there is no image source type to populate it from.
    If an 'image' source is ever added, that advisory becomes live.
    """
    from src.schemas.content import SourceType

    assert "image" not in get_args(SourceType), (
        "An image source type was added. podcastfy's image_url path (and therefore "
        "GHSA-2g6r) may now be reachable — re-check TRIAGED in "
        "scripts/pip_audit_gate.py before shipping."
    )


def test_no_caller_passes_image_paths_to_the_generation_task():
    """Second half of the guard above: the kwarg itself must stay unpopulated.

    Checked against the routers/services source rather than at runtime, since the
    point is that no code path exists that could supply it.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src"
    scanned = list((src / "routers").rglob("*.py")) + list(
        (src / "services").rglob("*.py")
    )
    # Without this the test passes vacuously if the layout moves and the globs
    # match nothing — a green "no offenders" that checked no files at all.
    assert len(scanned) > 10, (
        f"expected to scan the routers/services tree, found {len(scanned)} files "
        f"under {src} — has the layout changed?"
    )

    offenders = [
        f"{path.relative_to(src)}:{i}"
        for path in scanned
        for i, line in enumerate(path.read_text().splitlines(), 1)
        if "image_paths" in line
    ]
    assert not offenders, (
        "A router or service now passes image_paths into podcastfy, making the "
        f"image_url path (GHSA-2g6r) reachable: {offenders}"
    )
