# [P2.4] #489 — Adopt the react-hooks 7 rules (set-state-in-effect / incompatible-library)

Branch: `feature/issue-489-adopt-react-hooks-7-rules`. Plan source: self-authored (issue has DoD, no plan comment).

## Findings that shape the plan

- Real lint run (rules forced to `error`) reproduces the issue's 11 findings exactly: 10 `set-state-in-effect`,
  1 `incompatible-library`. No `exhaustive-deps` finding surfaces — that one was an artifact.
- Fixing `watch()` → `useWatch()` un-skips compilation of `episodes/[id]/page.tsx`, which **unmasks 2 more**
  `set-state-in-effect` findings there (the 4-loader auth effect and `setProgressMessage` in the SSE effect).
  True site count is **13**.
- Rule semantics (read from the plugin source, `validateNoSetStateInEffects`): a setState is flagged when it is
  reachable through the effect body's own blocks — including after `await`, inside `if`/`try` — or through a
  component-level function that directly calls setState (`useCallback` is erased first, so the async loaders
  count). setState inside a callback (`.then`, a listener) or a function declared inside the effect is not traced.
  So the async loaders are flagged only because the compiler cannot see across `await`; every flagged site is
  therefore restructured into a shape the compiler *can* verify, never suppressed.
- React docs' sanctioned fetch shape: `fetchX().then(r => { if (!ignore) setX(r) })` + `ignore = true` cleanup.
  That shape also closes a real stale-response race the current loaders have (analytics `days` switching,
  App Router reusing `episodes/[id]` across id changes).
- `enableAllowSetStateFromRefsInEffects` defaults on, but the loaders' `isMountedRef` guards don't dominate every
  setState (`setLoading(false)` in `finally`), so they don't rescue the episodes page.

## Design decisions (autonomous — no architectural fork)

| Site | Fix |
|---|---|
| dashboard, distribution, analytics, projects/[id], projects/[id]/distribution, episodes/[id] loaders | Split each `useCallback` loader into a module-level `fetchX()` that returns data-or-null (toasting on failure) and applies state in the effect's `.then` with an ignore flag. Handlers that refresh after a mutation keep a small `reloadX()`/`loadEpisode()` (setState in event handlers is fine). |
| distribution OAuth-return effect | Delete its `loadTargets()` — the auth effect already loads on mount, so this was a duplicate request. Its `exhaustive-deps` disable goes with it. |
| analytics `setLoading(true)` on `days` change | Moved into the `Select` change handler (issue option b). |
| episodes `setProgressMessage(STATUS_MESSAGES[status])` in SSE effect | Derive at render: `progressMessage \|\| STATUS_MESSAGES[status] \|\| "N% complete"`; `applyEpisode()` clears the transient SSE text when a fresh server snapshot lands. |
| episodes `watch("sourceType")` | `useWatch({ control, name: "sourceType" })` (react-hook-form 7.81 installed; compiler-compatible). |
| login `setRegistered` | Lazy `useState` initializer reads the URL; a `useSyncExternalStore` hydration gate keeps the server/client trees identical; the URL clear stays in an effect (external-system write, no setState). |
| AppleConnectDialog reset-on-open effect | Move form + instructions into an inner component rendered inside `DialogContent`; Radix unmounts it when closed, so state resets by remount and the fetch is a plain mount effect with an ignore flag. |
| theme-provider `mounted` / `resolvedTheme` | `useSyncExternalStore` over localStorage (custom + `storage` events) and over the `prefers-color-scheme` media query; `resolvedTheme` derived at render; the only effect left writes the `dark` class (external system). `mounted` disappears. Layout's nonce'd first-paint script is untouched. |
| eslint.config.mjs | Delete the two `'off'` lines and the #482 comment. |

Not doing: TanStack Query migration (installed but unwired; a bigger contract/test change than this lint adoption).

## Steps

1. RED: lint with the rules active (13 errors); jest tests for the new behaviour that fail today —
   analytics ignores a stale response after the period changes; distribution fetches targets once on OAuth return.
2. Flip `eslint.config.mjs` (remove the two `'off'` lines + comment).
3. Refactor the 8 files per the table.
4. GREEN: `npm run lint:web` clean, `npx jest` green, coverage on changed lines.
5. Deslop → quality gate (codex review; opencode has stalled 4/4 in this repo) → PR → demo → docs → CI → merge.

## Acceptance criteria (from #489)

- [ ] All findings resolved by refactor (not suppression), site list re-derived from a real run
- [ ] The two `'off'` lines and the comment naming #482 are deleted from `eslint.config.mjs`
- [ ] `npm run lint:web` clean with the rules active
- [ ] Jest suite still green, and any component whose render behaviour changed has its test checked
