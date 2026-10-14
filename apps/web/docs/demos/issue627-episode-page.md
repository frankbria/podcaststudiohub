# #627 — EpisodePage is decomposed and passes the CRAP gate

*2026-10-14T04:30:44Z by Showboat 0.6.1*
<!-- showboat-id: 6b392347-c787-4148-a623-dba70c2b106e -->

EpisodePage was ~1,000 lines at cc 58, so any change to the episode page failed the gate (#576 took an exception). It is now a thin page over hooks (use-episode, use-generation-progress, use-content-sources, use-tts-settings, use-episode-actions), an API module (episode-api.ts) and card/dialog components, all in the route folder. Highest complexity per file (lizard -l typescript):

```bash
for f in "src/app/(auth)/episodes/[id]"/*.ts*; do ~/.local/bin/lizard -l typescript "$f" 2>/dev/null | awk -v f="$(basename "$f")" '$2 ~ /^[0-9]+$/ && $6 ~ /@/ {if ($2>m) m=$2} END {print m, f}'; done | sort -rn | head -6
```

```output
5 episode-api.ts
5 TtsSettingsDialog.tsx
5 AnalyticsCard.tsx
4 use-tts-settings.ts
4 EpisodeHeaderCard.tsx
4 ContentSourcesCard.tsx
```

The unchanged page suite and the whole web suite:

```bash
npx jest "__tests__/app/episodes/\[id\]" 2>&1 | grep -E "^Tests:"; npx jest 2>&1 | grep -E "^Tests:"
```

```output
Tests:       60 passed, 60 total
Tests:       556 passed, 556 total
```
