# #621 — an episode is introduced as its project's show, not PODCASTIFY

*2026-10-14T03:04:30Z by Showboat 0.6.1*
<!-- showboat-id: 9719d89d-e607-4eff-a6a1-743caf276fb6 -->

The task now reads the project's show_title / description with the episode's other inputs and uses them as podcast_name / podcast_tagline when the template sets none. Against the real database and through the task with faked providers:

```bash
. /home/frankbria/.claude/jobs/a14abad9/tmp/testenv.sh && $PY -m pytest tests/test_native_inputs.py tests/unit/test_native_generation.py --no-cov -p no:cacheprovider -q -k 'show or podcast_name or introduced' 2>&1 | tail -1 | sed 's/ in .*//'
```

```output
====================== 4 passed, 23 deselected
```

One real script (Gemini) from the config the task builds for an episode with no template in a project titled 'The Signal Room':

```bash
. /home/frankbria/.claude/jobs/a14abad9/tmp/testenv.sh && export GEMINI_API_KEY="$(grep -E '^GEMINI_API_KEY=' /home/frankbria/projects/podcaststudiohub/.env | cut -d= -f2- | tr -d '"\r')" && PYTHONPATH=. $PY /home/frankbria/.claude/jobs/a14abad9/tmp/demo621.py 2>&1 | grep -v '"level"' | tail -2
```

```output
opening line: Welcome to The Signal Room! Today, we are looking at retrieval-augmented generation, or RAG. It basically ties a model's answer directly to fetched documents.
names the show: True | says PODCASTIFY: False
```
