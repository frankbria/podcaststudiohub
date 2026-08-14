"""Reachability guards for advisories in the podcastfy dependency closure (#446).

`scripts/security-audit.sh` ignores 24 advisory IDs that no bump can clear, because
`podcastfy==0.4.1` caps the whole langchain/litellm tree. Ignoring them is only
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
    )
    assert result.returncode == 0, (
        f"probe failed (exit {result.returncode})\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    return result.stdout


def test_litellm_proxy_is_not_reachable_from_the_generation_stack():
    """11 of the ignored advisories — including both criticals — are LiteLLM *proxy*
    issues (auth bypass, proxy config endpoints, /user/update, MCP test endpoints).

    They require running litellm as a proxy server. We import podcastfy's engine and
    never start a proxy, so the vulnerable modules must never even load. podcastfy
    reaches litellm only via langchain_community's ChatLiteLLM, which imports it
    lazily — so in practice litellm itself stays unimported too.
    """
    output = _run_probe(
        """
        import sys
        # The real generation entry points used by src/tasks/podcast_generation.py
        from podcastfy.client import generate_podcast          # noqa: F401
        from podcastfy.content_generator import ContentGenerator  # noqa: F401

        proxy = sorted(m for m in sys.modules if m.startswith("litellm.proxy"))
        print("PROXY_MODULES=" + (",".join(proxy) if proxy else "NONE"))
        """
    )
    assert "PROXY_MODULES=NONE" in output, (
        "litellm.proxy is now reachable from the generation stack. The proxy-only "
        "advisories ignored in scripts/security-audit.sh (incl. GHSA-4xpc-pv4p-pm3w "
        "and GHSA-jjhc-v7c2-5hh6, both critical) can no longer be treated as inert. "
        f"Probe output: {output!r}"
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
        "GHSA-2g6r) may now be reachable — re-check the ignore list in "
        "scripts/security-audit.sh before shipping."
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
