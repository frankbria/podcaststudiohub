# Issue #493 — Mutation-test the #492 error-boundary + relay tests

Plan source: issue body (mutation list). No architectural fork; approved autonomously.

## Steps
1. Worktree `../podcaststudiohub-wt-493`, branch `feature/issue-493-mutation-test-error-boundary` (issue process note: nothing else may edit the tree).
2. Script applies each of the 17 mutations to the implementation in turn, runs only the matching jest file, records KILLED/SURVIVED, restores the file.
3. For every SURVIVED mutation: add the smallest assertion that kills it, re-run the mutation, confirm KILLED.
4. Commit the record (`apps/web/docs/mutation-report-492.md`) + test changes; full web jest + lint green.
5. PR → review → demo (re-run script from the record) → CI → merge.

## Mutations (from issue)
- route.ts ×9: DSN gate, header event_id mismatch, drop exception, drop str() slice, String() coercion, drop Content-Length pre-check, drop Sec-Fetch-Site gate, drop fingerprint, drop !ingest.ok
- report-client-error.ts ×5: keepalive false, location.href, drop try/catch, drop truncation, change URL
- global-error.tsx ×2: drop html/body wrapper, drop reportClientError
- error.tsx ×1: drop reportClientError

## Acceptance
- [x] every mutation applied, matching test file run, result recorded (17/17 killed; PR #535 merged d9184a0)
- [x] an assertion added wherever no test failed (DSN gate survived run 1 as predicted; console.error-not-called assertion kills it)
