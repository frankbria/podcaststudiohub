---
on:
  issues:
    types: [opened, transferred]
  workflow_dispatch:
  roles: all
permissions:
  contents: read
  actions: read
safe-outputs:
  add-labels:
    allowed:
      - bug
      - enhancement
      - feature
      - documentation
      - question
      - priority-p0
      - priority-p1
      - priority-p2
      - priority-p3
      - phase-1
      - phase-2
      - phase-3
      - phase-4
      - phase-5
      - plan-ready
      - needs-info
      - needs-discussion
      - maintainer-autonomous
      - maintainer-notify
      - maintainer-approve
      - maintainer-human-only
      - security
      - breaking-change
      - architecture
    max: 6
  add-comment:
    max: 2
  assign-to-user:
    allowed: [frankbria]
    max: 1
  close-issue:
    target: "triggering"
---

# Issue Triage Agent

## Trigger Modes

**Issue event trigger**: When triggered by a new issue being opened or transferred, triage only that issue.

**Manual dispatch trigger**: When triggered via workflow_dispatch, fetch ALL open issues that have no labels yet (unlabeled), and triage each one. Skip issues that already have labels assigned.

## Context

This repository is **Podcastfy Studio Hub** — a platform for generating AI-powered podcasts from multi-modal content (websites, PDFs, YouTube, images, text). The codebase is a monorepo with:
- `/apps/api/` — FastAPI backend (Python)
- `/apps/web/` — Next.js frontend (TypeScript)

Read `.github/repo-maintainer/config.yml` for governance rules and current operating mode.

## Triage Instructions

For each issue, analyze the title and description to determine:

### 1. Classification
- **Bug reports**: Apply "bug" label. If critical (data loss, security, crash), also add "priority-p0".
- **Feature requests**: Apply "enhancement" or "feature" label.
- **Documentation**: Apply "documentation" label.
- **Support / unclear**: Apply "question" label, comment with guidance.
- **Duplicates**: Comment explaining which issue it duplicates and close it.

### 2. Priority Assignment
Based on severity, user impact, and scope:
- **priority-p0**: Critical — security vulnerability, data loss, complete feature broken
- **priority-p1**: High — major feature broken, significant user impact, blocks other work
- **priority-p2**: Medium — feature improvement, moderate impact, non-blocking
- **priority-p3**: Low — nice-to-have, cosmetic, minor improvement

### 3. Phase Assignment
Based on which area the issue affects:
- **phase-1**: Core podcast generation pipeline (content extraction, LLM generation, TTS)
- **phase-2**: API completeness (endpoints, validation, error handling)
- **phase-3**: Reliability & security (auth, rate limiting, error recovery)
- **phase-4**: Platform features (billing, analytics, collaboration, RSS)
- **phase-5**: UI/UX polish (accessibility, responsive design, animations)

### 4. Governance Tier
Read the governance rules from `.github/repo-maintainer/config.yml` and assign:
- **maintainer-autonomous**: Simple bugs (p2/p3), well-defined small changes
- **maintainer-notify**: Features (p1), moderate scope changes
- **maintainer-approve**: Critical issues (p0), security, breaking changes
- **maintainer-human-only**: Architecture decisions, issues needing discussion

### 5. Implementation Plan (if applicable)
If the issue is well-defined and classified as maintainer-autonomous or maintainer-notify:
1. Draft an implementation plan as a comment with:
   - Files likely to be modified
   - Approach summary (2-3 sentences)
   - Test strategy
2. Add the "plan-ready" label

If the issue is unclear or needs more information, add "needs-info" and ask specific clarifying questions.

### 6. Assignment
Assign bug reports with priority-p0 or priority-p1 to @frankbria.

## Comment Format

Add a triage comment with this structure:

```
**Triage Summary**

- **Type**: [bug/enhancement/documentation/question]
- **Priority**: [p0/p1/p2/p3]
- **Phase**: [1-5]
- **Governance**: [autonomous/notify/approve/human-only]

[Brief explanation of classification reasoning]

[If plan-ready: implementation plan]
```
