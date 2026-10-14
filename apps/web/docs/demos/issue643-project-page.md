# #643 — ProjectPage is decomposed and passes the CRAP gate

*2026-10-14T04:19:28Z by Showboat 0.6.1*
<!-- showboat-id: ca63a37d-5098-43f2-9953-76f32414a5f0 -->

ProjectPage measured cc 13, so any change to the project page failed the gate. It is now a data hook (useProjectData), request helpers sharing one toast/error path (sendRequest), and small components (ProjectSubNav, ProjectHeader, EpisodeList, EpisodeCard, StatusBadge, CreateEpisodeDialog, the edit/delete slots). Largest complexity left in the file:

```bash
~/.local/bin/lizard "src/app/(auth)/projects/[id]/page.tsx" 2>/dev/null | awk '$2 ~ /^[0-9]+$/ && $6 ~ /@/ {print $2, $6}' | sort -rn | head -4 | sed "s/@src.*//"
```

```output
15 renderCard@357-560
4 ProjectHeader@312-331
3 sendRequest@106-119
3 projectLoaded@185-189
```

The unchanged page suite (including the #529 remount test):

```bash
npx jest "__tests__/app/projects/\[id\]" 2>&1 | grep -E "^Tests:"
```

```output
Tests:       64 passed, 64 total
```
