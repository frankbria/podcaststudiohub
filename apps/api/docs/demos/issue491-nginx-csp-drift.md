# Issue #491: dev VPS serves two CSP headers — re-sync nginx + deploy drift gate

*2026-09-16T20:55:30Z*

Issue #491: the dev box's /etc/nginx/sites-available/podcastfy predates #307, so every document response carries a second, static CSP with script-src 'unsafe-inline' on top of the middleware's nonce policy. Before touching anything, the reproduction from the issue (expect 2):

```bash
curl -sI https://dev.podcaststudiohub.me/login | grep -ci content-security-policy
```

```output
2
```

The new deploy-side check (deployment/scripts/check-nginx-drift.sh) ssh-reads the installed file and diffs it against the committed conf. Run against the box as it stands, it fails loudly and names both stale CSP lines and the missing /ready block (exit 1; only the CSP/ready hunks and the footer are shown):

```bash
SSH_HOST=staging-ts SSH_USER=root bash deployment/scripts/check-nginx-drift.sh 2>&1 | grep -nE "^[-+].*(Content-Security-Policy|location /ready)|^❌|sudo (git|cp|nginx)" | cut -c1-130; echo "exit=${PIPESTATUS[0]}"
```

```output
25:-	add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';
26:+	# NO Content-Security-Policy here (issue #307): the document CSP is a
51:+	location /ready {
63:-		add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';
66:+		add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src
71:❌ nginx config drift (issue #491): /etc/nginx/sites-available/podcastfy on staging-ts does not match
75:     sudo git -C /root/podcaststudiohub pull
76:     sudo cp /root/podcaststudiohub/deployment/nginx/podcastfy.conf /etc/nginx/sites-available/podcastfy
77:     sudo nginx -t && sudo systemctl reload nginx
exit=1
```

Operator re-sync done on the box (root, from the root-owned clone: git pull → cp deployment/nginx/podcastfy.conf into sites-available → nginx -t → reload; nginx -t warned only that ssl_stapling is ignored because Let's Encrypt certificates no longer carry an OCSP responder URL — pre-existing, unrelated). AC: exactly one CSP header on a document response (expect 1):

```bash
curl -sI https://dev.podcaststudiohub.me/login | grep -ci content-security-policy
```

```output
1
```

AC: the remaining header is the middleware's nonce policy — script-src carries a per-request nonce and 'strict-dynamic', and 'unsafe-inline' is gone from script-src:

```bash
curl -sI https://dev.podcaststudiohub.me/login | grep -i '^content-security-policy' | grep -oE "script-src [^;]+" | sed -E "s/nonce-[A-Za-z0-9+/=]+/nonce-<per-request>/"; echo "unsafe-inline in script-src: $(curl -sI https://dev.podcaststudiohub.me/login | grep -i '^content-security-policy' | grep -oE 'script-src [^;]+' | grep -c unsafe-inline)"
```

```output
script-src 'self' 'nonce-<per-request>' 'strict-dynamic'
unsafe-inline in script-src: 0
```

AC: /static/ still carries its own strict no-inline CSP from nginx (add_header … always, so it shows even on a 404 for a non-existent asset):

```bash
curl -sI https://dev.podcaststudiohub.me/static/probe.js | grep -iE '^(HTTP|content-security-policy)' | cut -c1-110
```

```output
HTTP/2 404
content-security-policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-s
```

AC: the deploy gate now passes against the re-synced box (this is the exact command the last step of deploy-dev.yml runs; exit 0):

```bash
SSH_HOST=staging-ts SSH_USER=root bash deployment/scripts/check-nginx-drift.sh; echo "exit=$?"
```

```output
✓ nginx config on staging-ts matches deployment/nginx/podcastfy.conf
exit=0
```

And the gate's own tests — script contract, provisioning-substitution parity, workflow wiring, and a functional run against an ssh shim where an in-sync box passes and a drifted one fails with the offending line:

```bash
python3 -m pytest deployment/tests/test_nginx_drift.py -q 2>&1 | tail -1
```

```output
10 passed in 0.07s
```
