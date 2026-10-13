# #529 — episode and project pages remount when the route id changes

*2026-10-13T21:54:32Z by Showboat 0.6.1*
<!-- showboat-id: 09406113-026f-4a4b-b8fd-8ad8982a09e7 -->

The App Router reuses a page instance when only `[id]` changes, so a page whose `loading` flag is only ever `true` at mount kept the previous entity on screen until the new fetch landed. Each page now has a default-export route wrapper that renders it with `key={params.id}`, so an id change remounts it into its skeleton. The tests render a page with id 1, wait for its content, switch `useParams` to id 2 (whose fetches never resolve), rerender, and assert the skeleton (`aria-label="Loading"`) is shown with no stale title. On `main` both fail.

```bash
npx jest "__tests__/app/episodes/\[id\]/page.test.tsx" "__tests__/app/projects/\[id\]/page.test.tsx" -t "529|App Router swaps" --verbose 2>&1 | grep -E "✓|✕|Tests:"
```

```output
Tests:       83 skipped, 3 passed, 86 total
```
