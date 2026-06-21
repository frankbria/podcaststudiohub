"""
IP-pinned outbound fetch helpers (issue #234).

The SSRF guard (``src.utils.ssrf.validate_public_url``) resolves a URL's host and
rejects it if any resolved address is non-public. But the underlying HTTP clients
(``requests``, ``httpx``) re-resolve the hostname at connect time, so a TTL-0
DNS-rebinding attacker can return a public IP to the guard and an internal IP
(e.g. 169.254.169.254) to the real connection — a TOCTOU window.

These helpers close that window by forcing the connection to the IP the guard
already validated, while preserving TLS correctness: the original ``Host`` header
(virtual hosting), SNI, and certificate verification all stay bound to the
*hostname*, not the IP.

Pinning is per-connection / per-request — there is no process-wide
``getaddrinfo`` monkeypatching, so it is safe under the Celery worker / threadpool
concurrency model.
"""

from typing import Dict, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter


def _ip_netloc(ip: str, port: Optional[int]) -> str:
	"""Build a netloc for ``ip``, bracketing IPv6 and appending ``port`` if set."""
	host = f"[{ip}]" if ":" in ip else ip
	return f"{host}:{port}" if port else host


class _PinnedIPAdapter(HTTPAdapter):
	"""
	A ``requests`` transport adapter that connects to a fixed IP.

	The request URL's host is rewritten to ``ip`` so the socket connects only to
	the validated address (an IP literal — no further DNS lookup). The original
	``Host`` header is preserved, and for HTTPS the urllib3 pool is configured to
	use the hostname for SNI and certificate verification.
	"""

	def __init__(self, hostname: str, ip: str, tls: bool, **kwargs):
		# Set before super().__init__, which calls init_poolmanager().
		self._hostname = hostname
		self._ip = ip
		self._tls = tls
		super().__init__(**kwargs)

	def init_poolmanager(self, *args, **kwargs):
		if self._tls:
			# Verify the cert and send SNI for the hostname even though the
			# connection targets the IP (urllib3 advanced-usage recipe).
			kwargs["server_hostname"] = self._hostname
			kwargs["assert_hostname"] = self._hostname
		super().init_poolmanager(*args, **kwargs)

	def send(self, request, **kwargs):
		parsed = urlparse(request.url)
		# Defense in depth: urlparse already strips CR/LF, but never let a
		# control character reach the Host header (request smuggling).
		if any(ord(c) < 32 or c == "\x7f" for c in parsed.netloc):
			raise ValueError(f"Invalid control character in URL host: {parsed.netloc!r}")
		# Preserve virtual hosting + the cert/SNI host via the Host header...
		request.headers["Host"] = parsed.netloc
		# ...while connecting to the pre-validated IP literal.
		request.url = urlunparse(
			parsed._replace(netloc=_ip_netloc(self._ip, parsed.port))
		)
		return super().send(request, **kwargs)


def pinned_session(url: str, ip: str) -> requests.Session:
	"""
	Return a ``requests.Session`` whose connections to ``url``'s host are pinned
	to ``ip`` (TLS still verified against the hostname).

	``ip`` must be an address already validated by ``validate_public_url`` for
	this exact URL — pinning to an unvalidated IP would defeat the guard.
	"""
	parsed = urlparse(url)
	hostname = parsed.hostname
	if not hostname:
		raise ValueError(f"Cannot pin a URL without a host: {url!r}")
	session = requests.Session()
	adapter = _PinnedIPAdapter(hostname, ip, tls=(parsed.scheme == "https"))
	session.mount(f"{parsed.scheme}://", adapter)
	return session


def pin_httpx(
	url: str, ip: str
) -> Tuple[str, Dict[str, str], Dict[str, str]]:
	"""
	Build the ``(url, headers, extensions)`` needed to make an ``httpx`` request
	connect to ``ip`` while verifying TLS against ``url``'s hostname.

	httpx's ``sni_hostname`` request extension makes SSL verification use the
	hostname even though the URL targets the IP (httpx advanced/extensions docs).

	``ip`` must be an address already validated by ``validate_public_url`` for
	this exact URL.
	"""
	parsed = urlparse(url)
	hostname = parsed.hostname
	if not hostname:
		raise ValueError(f"Cannot pin a URL without a host: {url!r}")
	pinned_url = urlunparse(parsed._replace(netloc=_ip_netloc(ip, parsed.port)))
	headers = {"Host": parsed.netloc}
	extensions = {"sni_hostname": hostname}
	return pinned_url, headers, extensions
