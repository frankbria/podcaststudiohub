# #564 — the deploy prunes superseded Node 24.x patches

*2026-10-14T02:48:16Z by Showboat 0.6.1*
<!-- showboat-id: 5c3a6048-f981-44d7-9c95-a85af454fe5c -->

The prune snippet from deploy-dev.yml, run against the real nvm.sh in a throwaway NVM_DIR holding five fake versions. v24.12.0 is running: it and the newest other 24.x (v24.11.0) stay, v22 is not touched.

```bash
bash /home/frankbria/.claude/jobs/a14abad9/tmp/nvm-demo.sh $PWD 2>&1 | tail -7
```

```output
before:  v22.5.0 v24.9.0 v24.10.0 v24.11.0 v24.12.0
current: v24.12.0
pruning superseded node v24.9.0
Uninstalled node v24.9.0
pruning superseded node v24.10.0
Uninstalled node v24.10.0
after:   v22.5.0 v24.11.0 v24.12.0
```

The pinned tests: keeps the running node plus one prior (version order), never removes the running node even when it is not the newest, leaves other majors alone, and runs inside the restart heredoc after pm2 start.

```bash
python3 -m pytest deployment/tests/test_node_runtime.py -q -p no:cacheprovider 2>&1 | tail -1 | sed 's/ in .*//'
```

```output
17 passed
```

On the dev server today (read-only): one 24.x version installed, so the first deploy prunes nothing.

```bash
ssh root@staging 'ls -1 /home/podcastfy/.nvm/versions/node'
```

```output
v24.21.0
```
