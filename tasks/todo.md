# Issue #226 — fix(web): design tokens + robustness nits

Branch: `fix/226-web-design-tokens-robustness`
Plan source: self-authored (issue had only an empty CodeRabbit planner prompt).

## Acceptance criteria (hard gate)
- [ ] Replace gray classes with `bg-background`/`text-foreground`/`text-muted-foreground`
- [ ] Wrap download click+cleanup in try/finally
- [ ] Trim `fullName` in signup

## Plan (TDD: test first where it adds value)

1. **page.tsx** (`src/app/page.tsx:22-25`) — replace `bg-gray-50`→`bg-background`,
   `text-gray-900`→`text-foreground`, `text-gray-600`→`text-muted-foreground`.
   Verify: grep shows no `gray-` left in changed files.

2. **download.ts** (`src/lib/download.ts:33-39`) — wrap appendChild/click/removeChild
   in try, move `removeChild` + `revokeObjectURL` into `finally`.
   Test: removeChild throws → revokeObjectURL still called (extend download.test.ts).

3. **signup/page.tsx** (line 27) — send `full_name: fullName.trim()`.
   Test: padded fullName → request body has trimmed value
   (extend __tests__/app/signup/page.test.tsx).

4. **episodes/[id]/page.tsx** — review item. Add `isMountedRef` guard: set false on
   unmount; early-return in `handleMessage` and guard `setEpisode` in `loadEpisode`
   so SSE-driven async callbacks don't setState after unmount.

## Quality gate
- `npm test` (jest), `npm run lint`, `npx tsc --noEmit`
- cross-family review (codex/coderabbit), demo, CI green → merge
