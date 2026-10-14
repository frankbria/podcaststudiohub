# #643 — ProjectPage is decomposed and passes the CRAP gate

*2026-10-14T04:21:01Z by Showboat 0.6.1*
<!-- showboat-id: a6cf332d-96b5-4ad5-bab0-e9c1165f51a7 -->

ProjectPage measured cc 13, so any change to the project page failed the gate. It is now a data hook (useProjectData), request helpers sharing one toast/error path (sendRequest), and small components (ProjectSubNav, ProjectHeader, EpisodeList, EpisodeCard, StatusBadge, CreateEpisodeDialog, the edit/delete slots). Largest complexity left in the file (lizard):

```bash
~/.local/bin/lizard "src/app/(auth)/projects/[id]/page.tsx" 2>/dev/null | awk '$2 ~ /^[0-9]+$/ && $6 ~ /@/ {print $2, $6}' | sort -rn | head -4 | sed "s/@src.*//"
```

```output
5 EpisodeTitleField@500-523
4 ProjectHeader@312-331
4 CreateEpisodeDialog@443-526
3 sendRequest@106-119
```

The unchanged page suite (including the #529 remount test):

```bash
npx jest "__tests__/app/projects/\[id\]" 2>&1 | grep -E "^Tests:"
```

```output
Tests:       64 passed, 64 total
```
