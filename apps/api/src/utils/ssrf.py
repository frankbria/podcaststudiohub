"""
SSRF (Server-Side Request Forgery) guard utilities.

User-supplied URLs (content sources, webhook distribution targets) are fetched
server-side. Without protection an authenticated tenant user could point them at
loopback, link-local, private, or reserved addresses — notably the cloud
metadata endpoint http://169.254.169.254/ — to read internal services or trigger
internal POST endpoints (issue #206).

This module resolves a URL's host and rejects it if *any* resolved address is
not a public/global IP, or if the scheme/port is not allowed. It is invoked at
both validation time (before persisting a source/target) and dispatch time
(immediately before the outbound request) so that DNS rebinding between the two
points is also caught.

Unresolvable hosts (NXDOMAIN) are intentionally *allowed* here: there is no IP
to connect to, so they are not an SSRF target, and rejecting them would break
legitimate not-yet-provisioned hostnames. The actual fetch fails naturally, and
a host that later resolves to an internal IP is caught by the dispatch-time
re-check.
"""

import ipaddress
import logging
import socket
from typing import Iterable, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SSRFValidationError(ValueError):
	"""Raised when a URL targets a disallowed (internal/non-public) address."""

	pass


# Default ports permitted for outbound fetches. Non-standard ports are rejected
# to prevent reaching internal services bound to unusual ports.
DEFAULT_ALLOWED_SCHEMES = ("http", "https")
DEFAULT_ALLOWED_PORTS = frozenset({80, 443})

# Default port to assume when a URL omits one, keyed by scheme.
_SCHEME_DEFAULT_PORTS = {"http": 80, "https": 443}


def is_public_ip(ip: str) -> bool:
	"""
	Return True only if ``ip`` is a globally routable public address.

	Rejects loopback, link-local (incl. 169.254.169.254), private (RFC1918 /
	ULA / CGNAT), reserved, multicast, and unspecified addresses. IPv4-mapped
	IPv6 addresses are unwrapped and evaluated as their IPv4 form.
	"""
	try:
		addr = ipaddress.ip_address(ip)
	except ValueError:
		return False

	# Unwrap IPv4-mapped IPv6 (e.g. ::ffff:169.254.169.254) so the embedded
	# IPv4 address is evaluated against the same rules.
	if addr.version == 6:
		mapped = getattr(addr, "ipv4_mapped", None)
		if mapped is not None:
			addr = mapped

	# is_global is the authoritative "globally reachable" check: it excludes
	# loopback, link-local (incl. 169.254.169.254), private (RFC1918 / ULA),
	# CGNAT (100.64/10), reserved, multicast, and unspecified ranges.
	return addr.is_global


def _resolve_host(host: str, port: Optional[int]) -> List[str]:
	"""
	Resolve ``host`` to its IP addresses.

	Returns the list of resolved IP strings, or an empty list if the host
	cannot be resolved (NXDOMAIN). IP-literal hosts resolve without network
	access.
	"""
	try:
		infos = socket.getaddrinfo(host, port or 0, proto=socket.IPPROTO_TCP)
	except socket.gaierror:
		return []
	return sorted({info[4][0] for info in infos})


def validate_public_url(
	url: str,
	*,
	allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
	allowed_ports: Iterable[int] = DEFAULT_ALLOWED_PORTS,
	block_on_resolution_failure: bool = False,
) -> List[str]:
	"""
	Validate that ``url`` targets only public addresses on an allowed scheme/port.

	Args:
		url: The URL to validate.
		allowed_schemes: Permitted URL schemes (default http + https).
		allowed_ports: Permitted ports (default 80 + 443). A URL without an
			explicit port uses the scheme's default port for this check.
		block_on_resolution_failure: When True, an unresolvable host raises
			rather than being allowed. Use this on dispatch paths (the actual
			outbound fetch), where a host that fails the guard's lookup but
			resolves to an internal IP on the real request would otherwise slip
			through. Validation-time callers leave this False so not-yet-
			provisioned hostnames are not rejected outright.

	Returns:
		The list of resolved public IP addresses (empty only when the host is
		unresolvable and ``block_on_resolution_failure`` is False).

	Raises:
		SSRFValidationError: If the scheme/port is not allowed, any resolved
			address is not a public IP, or the host is unresolvable while
			``block_on_resolution_failure`` is True.
	"""
	if not url or not url.strip():
		raise SSRFValidationError("URL cannot be empty")

	try:
		parsed = urlparse(url)
	except ValueError as exc:
		raise SSRFValidationError(f"Invalid URL: {exc}") from exc

	allowed_schemes = tuple(s.lower() for s in allowed_schemes)
	scheme = (parsed.scheme or "").lower()
	if scheme not in allowed_schemes:
		raise SSRFValidationError(
			f"URL scheme '{parsed.scheme}' is not allowed "
			f"(allowed: {', '.join(allowed_schemes)})"
		)

	host = parsed.hostname
	if not host:
		raise SSRFValidationError("URL is missing a host")

	try:
		port = parsed.port
	except ValueError as exc:
		raise SSRFValidationError(f"Invalid port in URL: {exc}") from exc

	effective_port = port if port is not None else _SCHEME_DEFAULT_PORTS.get(scheme)
	allowed_ports = frozenset(allowed_ports)
	if effective_port not in allowed_ports:
		raise SSRFValidationError(
			f"URL port {effective_port} is not allowed "
			f"(allowed: {', '.join(str(p) for p in sorted(allowed_ports))})"
		)

	resolved = _resolve_host(host, effective_port)
	if not resolved and block_on_resolution_failure:
		raise SSRFValidationError(
			f"URL host '{host}' could not be resolved and cannot be fetched"
		)
	for ip in resolved:
		if not is_public_ip(ip):
			raise SSRFValidationError(
				f"URL host '{host}' resolves to a non-public address "
				f"and cannot be fetched"
			)

	return resolved
