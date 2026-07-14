"""Guard against nginx upstream port drift (issue #317).

The committed ``podcastfy.conf`` bakes the dev ports (API 8005, web 3010) and
``provision-ssl.sh`` substitutes ``API_PORT``/``FRONTEND_PORT`` overrides into
the installed copy. These tests pin the two sides together so the conf, the
script defaults, and the substitution mechanism cannot silently diverge again
(the original drift shipped 8001/3003 upstreams → 502s on the dev host).
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "provision-ssl.sh"


def _script_text() -> str:
	return SCRIPT_PATH.read_text()


def _script_default(var: str) -> str:
	m = re.search(rf'{var}="\$\{{{var}:-(\d+)\}}"', _script_text())
	assert m, f"provision-ssl.sh must define {var}=\"${{{var}:-<port>}}\""
	return m.group(1)


def test_api_upstream_port_matches_script_default(nginx_conf_raw: str):
	m = re.search(
		r"upstream\s+podcastfy_api\s*\{[^}]*?server\s+127\.0\.0\.1:(\d+)", nginx_conf_raw
	)
	assert m, "podcastfy.conf must define the podcastfy_api upstream"
	assert m.group(1) == _script_default("API_PORT"), (
		"API upstream port in podcastfy.conf must equal the API_PORT default in "
		"provision-ssl.sh (drift here 502s the API — issue #317)"
	)


def test_frontend_proxy_ports_match_script_default(nginx_conf_raw: str):
	# Set-equality is deliberate: every direct-IP proxy_pass must be the
	# frontend — the API must go through the podcastfy_api upstream, so a new
	# direct-IP API proxy_pass should fail here.
	ports = set(re.findall(r"proxy_pass\s+http://127\.0\.0\.1:(\d+)", nginx_conf_raw))
	assert ports, "podcastfy.conf must proxy_pass to the Next.js app"
	assert ports == {_script_default("FRONTEND_PORT")}, (
		"every direct proxy_pass port in podcastfy.conf must equal the "
		"FRONTEND_PORT default in provision-ssl.sh (drift here 502s the frontend "
		f"— issue #317); found ports: {sorted(ports)}"
	)


def test_script_substitutes_both_port_overrides():
	text = _script_text()
	for var in ("API_PORT", "FRONTEND_PORT"):
		assert re.search(rf"sed .*\${{{var}}}", text), (
			f"provision-ssl.sh must sed-substitute ${{{var}}} into the installed "
			"nginx site (same contract as the DOMAIN override)"
		)


def test_no_stale_bootstrap_ports():
	assert "8001" not in _script_text() and "3003" not in _script_text(), (
		"provision-ssl.sh must not hardcode the retired 8001/3003 ports "
		"(issue #317)"
	)
