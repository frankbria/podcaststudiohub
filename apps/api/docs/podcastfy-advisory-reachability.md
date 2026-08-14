# Reachability of the podcastfy-capped advisories

**Date:** 2026-08-13 · **Issue:** #446 · **Companion:** [podcastfy-fork-effort-review.md](./podcastfy-fork-effort-review.md)

`scripts/security-audit.sh` ignores 24 advisory IDs because `podcastfy==0.4.1` caps the
whole langchain/litellm tree (see [podcastfy-0.4.3-evaluation.md](./podcastfy-0.4.3-evaluation.md)
and #363). Ignoring an advisory is only defensible if the vulnerable code is genuinely
unreachable from our call paths. This document records that assessment.

**Headline: 21 of 22 open Dependabot alerts are unreachable. One is reachable.**

The "2 critical" figure in #446's original title is misleading — both criticals are inert.
The one advisory that matters is a *high* that the blanket "structurally capped" framing
was hiding.

## Verification method

Claims here are verified, not assumed:

```bash
# no litellm usage in our source at all — it is purely transitive
grep -rn "litellm" apps/api/src --include="*.py"        # -> no matches

# the cap is real, not an artifact of the lockfile
uv lock --upgrade-package 'litellm>=1.81.0'             # -> unsatisfiable (needs openai>=2.20 vs podcastfy's openai<2)
uv lock --upgrade-package 'langsmith>=0.7.31'           # -> unsatisfiable
uv lock --upgrade-package 'pytest>=9.0.3'               # -> unsatisfiable
uv lock --upgrade-package 'langchain-core>=1.2.11'      # -> unsatisfiable
```

The import-graph claims are enforced by `tests/test_dependency_reachability.py`, so they
cannot silently rot.

## Unreachable (21)

### LiteLLM proxy server — 11 advisories, including both criticals

| ID | Sev | Summary |
|---|---|---|
| GHSA-4xpc-pv4p-pm3w | critical | Auth bypass via Host header injection |
| GHSA-jjhc-v7c2-5hh6 | critical | Auth bypass via OIDC userinfo cache key collision |
| GHSA-53mr-6c8q-9789 | high | Privilege escalation via unrestricted proxy config endpoints |
| GHSA-69x8-hrgq-fjj8 | high | Password hash exposure / pass-the-hash bypass |
| GHSA-7488-6r32-c95q | high | MCP auth bypass via OAuth2 passthrough fallback |
| GHSA-qrc4-49gv-mv9m | high | internal_user can create over-scoped API keys |
| GHSA-v4p8-mg3p-g94g | high | Authenticated command execution via MCP stdio test endpoints |
| GHSA-wpfp-gwwc-vwq6 | high | User can modify own `user_role` via `/user/update` |
| GHSA-5jmr-gcrj-2c9q | medium | Path traversal in Skills archive extraction |
| GHSA-4g5m-c9r5-49xf | low | Local file read via request-supplied OIDC file references |
| GHSA-72m8-9m7m-h278 | low | Custom Code Guardrails endpoint bypass |

Every one requires running **litellm as a proxy server** with its management API exposed.
We never do: no litellm import in our source, no proxy config file, no proxy process in
PM2 or the deploy workflow. `litellm/proxy/` ships on disk but never executes.

In fact litellm itself is never imported — podcastfy reaches it through
`langchain_community.chat_models.ChatLiteLLM`, which imports lazily. Verified with the
full engine loaded (`podcastfy.client` + `ContentGenerator`): `litellm` absent from
`sys.modules`.

> **GHSA-jjhc** additionally requires `enable_jwt_auth: true`, which upstream notes is off
> by default: *"Most instances are not affected."*

### Unused features — 9 advisories

| ID | Sev | Package | Why unreachable |
|---|---|---|---|
| GHSA-qv8j-hgpc-vrq8 | high | google-cloud-aiplatform | No vertex/aiplatform usage in our source |
| GHSA-wh2j-26j7-9728 | high | google-cloud-aiplatform | Same |
| GHSA-pc6w-59fv-rh23 | high | langchain-community | XXE in loaders we never call |
| GHSA-qh6h-p6c9-ff54 | high | langchain-core | Legacy `load_prompt` — never called |
| GHSA-f4xh-w4cj-qxq8 | high | langsmith | `TracingMiddleware` — tracing never configured |
| GHSA-rr7j-v2q5-chgv | medium | langsmith | Streaming redaction — tracing never configured |
| GHSA-gr75-jv2w-4656 | medium | langchain | File-search middleware — not used |
| GHSA-fv5p-p927-qmxr | medium | langchain-text-splitters | `HTMLHeaderTextSplitter.split_text_from_url` — not used |
| GHSA-2g6r-c272-w58r | low | langchain-core | SSRF via `image_url` token counting — see below |

**GHSA-2g6r** deserves a note. podcastfy *does* build `image_url` message parts
(`content_generator.py:805`), but only when `image_paths` is non-empty.
`generate_podcast_task` accepts that kwarg and no caller ever populates it, because
`SourceType` is `Literal['url', 'pdf', 'text']` — there is no image source to populate it
from. **If an image source type is ever added, this advisory goes live.** Guarded by
`test_no_image_source_type_keeps_the_image_url_path_unreachable` and
`test_no_caller_passes_image_paths_to_the_generation_task`.

### Test-only — 1 advisory

`GHSA-6w46-j5rx-g56g` (medium, pytest `tmpdir` handling). pytest is in the *runtime*
closure only because podcastfy declares it as a runtime dependency — a packaging defect
upstream, not something we execute in production.

## Reachable (1) — accepted risk

### GHSA-3644-q5cj-c5c7 · high · langsmith 0.3.45 (fix: 0.8.0, unreachable)

> LangSmith SDK: Public prompt pull deserializes untrusted manifests without validation.

**This is on the main generation path.** podcastfy fetches its prompt templates from
LangChain Hub at runtime:

```python
# podcastfy/content_generator.py:565-566, 790
clean_transcript_prompt = hub.pull(f"{...['cleaner_prompt_template']}:{...['cleaner_prompt_commit']}")
rewrite_prompt          = hub.pull(f"{...['rewriter_prompt_template']}:{...['rewriter_prompt_commit']}")
prompt_template         = hub.pull(f"{template}:{commit}")
```

against a third-party account (`podcastfy/config.yaml`):

```yaml
prompt_template:         "souzatharsis/podcastfy_multimodal_cleanmarkup"   # commit b2365f11
longform_prompt_template:"souzatharsis/podcastfy_longform"                 # commit acfdbc91
cleaner_prompt_template: "souzatharsis/podcastfy_longform_clean"           # commit 8c110a0b
rewriter_prompt_template:"souzatharsis/podcast_rewriter"                   # commit 8ee296fb
```

**Decision: accepted, not mitigated.** Rationale:

- Every pull is **pinned to a specific commit**, so exploitation requires an attacker to
  alter the content behind an existing pinned commit, not merely to push a new revision.
  That is a materially higher bar than the advisory's unpinned worst case.
- No fix is reachable — langsmith is capped at 0.3.45 by podcastfy's `langchain-community
  <0.4`, and upstream podcastfy is dormant (0.4.3, 2025-12-09; nothing in 8 months).
- Mitigating it properly means removing the runtime hub dependency, which changes
  generation behaviour and belongs with the fork decision, not with a dependency bump.

**Two non-security consequences of the same code, worth knowing:**

1. **Availability.** Generation depends on LangChain Hub being up and on a third party's
   account continuing to exist. The two pulls at :565-566 are wrapped in `try/except` and
   degrade to the raw transcript; the pull at **:790 is not wrapped** and will propagate.
2. **Egress.** Every episode makes outbound calls to LangChain Hub. Any future network
   lockdown must allowlist it or generation breaks.

## Re-check triggers

Re-run this assessment when any of these change:

- podcastfy is bumped or forked → the whole cap disappears; redo from scratch
- an **image** source type is added → GHSA-2g6r goes live (tests will fail)
- litellm is imported directly, or a litellm proxy is deployed → 11 advisories go live
  (test will fail)
- LangSmith tracing is enabled (`LANGCHAIN_TRACING_V2`, `LANGSMITH_API_KEY`) → 2 langsmith
  advisories go live
- Vertex AI / `aiplatform` is adopted → 2 advisories go live
