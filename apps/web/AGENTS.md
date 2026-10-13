# apps/web: Next.js-managed agent rules

`next dev` writes the block below whenever it runs under an AI coding agent
(Next 16's `generate-agent-files.js`, gated on agent detection). This file
exists so it lands here and never in `CLAUDE.md`, which stays hand-curated
(#494). Do not edit between the markers: Next rewrites that span when its text
changes on an upgrade. Commit the change when it does.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
