# Issue #317: nginx upstream port drift — parameterized provisioning + drift gate

*2026-07-14T05:17:25Z*

Issue #317: provision-ssl.sh used to install the committed nginx conf with hardcoded upstreams (8001/3003) that did not match the deployed ports (8005/3010), causing 502s. AC1: the conf now commits the real dev defaults and provision-ssl.sh substitutes API_PORT/FRONTEND_PORT overrides the same way it substitutes DOMAIN. First, the committed defaults and the new override variables:

```bash
grep -nE '127\.0\.0\.1:[0-9]+' deployment/nginx/podcastfy.conf | head -4
```

```output
19:	server 127.0.0.1:8005;
87:		proxy_pass http://127.0.0.1:3010;
130:		proxy_pass http://127.0.0.1:3010;
140:		proxy_pass http://127.0.0.1:3010;
```

```bash
grep -n 'PORT=' deployment/scripts/provision-ssl.sh | head -4
```

```output
26:API_PORT="${API_PORT:-8005}"
27:FRONTEND_PORT="${FRONTEND_PORT:-3010}"
```

The defaults match the deploy workflow ports (8005/3010) exactly. Now the override path — the script rewrites the installed copy with the same guarded sed pattern used for DOMAIN. Simulating an install with API_PORT=9001 FRONTEND_PORT=4000 by running the exact substitution lines from the script against a copy of the conf:

```bash
grep -A7 'Honour port overrides' deployment/scripts/provision-ssl.sh
```

```output
# Honour port overrides the same way: rewrite the conf's committed dev
# defaults (8005/3010) to this environment's upstream ports.
if [ "${API_PORT}" != "8005" ]; then
	sed -i "s/127\.0\.0\.1:8005/127.0.0.1:${API_PORT}/g" "${NGINX_SITE}"
fi
if [ "${FRONTEND_PORT}" != "3010" ]; then
	sed -i "s/127\.0\.0\.1:3010/127.0.0.1:${FRONTEND_PORT}/g" "${NGINX_SITE}"
fi
```

```bash
export NGINX_SITE=$(mktemp) API_PORT=9001 FRONTEND_PORT=4000
cp deployment/nginx/podcastfy.conf "$NGINX_SITE"
eval "$(grep -A7 "Honour port overrides" deployment/scripts/provision-ssl.sh)"
grep -nE "127\.0\.0\.1:[0-9]+" "$NGINX_SITE"; rm -f "$NGINX_SITE"
```

```output
19:	server 127.0.0.1:9001;
87:		proxy_pass http://127.0.0.1:4000;
130:		proxy_pass http://127.0.0.1:4000;
140:		proxy_pass http://127.0.0.1:4000;
```

AC2: a regression test pins the conf ports to the script defaults so drift is caught in CI. First, the gate passing on the fixed tree:

```bash
python -m pytest deployment/tests/test_port_alignment.py -q 2>&1 | tail -2
```

```output
/home/frankbria/.local/share/uv/tools/showboat/bin/python: No module named pytest
```

Mutation check — reintroduce the original bug (upstream back to 8001) and the gate fails loudly, then restore:

```bash
/usr/bin/python -m pytest deployment/tests/test_port_alignment.py -q 2>&1 | tail -2
```

```output
....                                                                     [100%]
4 passed in 0.02s
```

Mutation check — reintroduce the original bug (upstream back to 8001) and the gate fails loudly, then restore:

```bash
sed -i "s/127\.0\.0\.1:8005/127.0.0.1:8001/" deployment/nginx/podcastfy.conf
/usr/bin/python -m pytest deployment/tests/test_port_alignment.py -q 2>&1 | grep -E "^FAILED|assert .* == |failed" | head -3
git checkout -- deployment/nginx/podcastfy.conf
echo "--- restored ---"
/usr/bin/python -m pytest deployment/tests/test_port_alignment.py -q 2>&1 | tail -1
```

```output
>   	assert m.group(1) == _script_default("API_PORT"), (
E    assert '8001' == '8005'
FAILED deployment/tests/test_port_alignment.py::test_api_upstream_port_matches_script_default
--- restored ---
4 passed in 0.02s
```

The gate catches the exact bug from the issue (assert 8001 == 8005) and the stale-port check also guards the provisioning script itself. Full deployment suite, including real nginx -t in Docker:

```bash
/usr/bin/python -m pytest deployment/tests/ -q 2>&1 | tail -1
```

```output
42 passed in 1.23s
```
