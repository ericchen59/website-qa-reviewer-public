"""Fetch policy for vendoring: what the fetcher may request with the PMM's browser session.

http and https only; no loopback, private, link-local or metadata addresses (checked after
DNS resolution, and again on the final URL after redirects); caps on request count and total
bytes. The fetch it wraps returns (final_url, bytes).
"""

import ipaddress
import socket
from urllib.parse import urlsplit


class PolicyError(ValueError):
    pass


def _blocked(ip: str) -> bool:
    a = ipaddress.ip_address(ip.split("%")[0])
    # is_global already covers private/loopback/link-local/reserved/unspecified, and also
    # ranges the old enumerated flags missed -- e.g. 100.64.0.0/10 (CGNAT, Tailscale), which
    # is_private does not flag. is_global alone does count some multicast as "global" though,
    # so that stays an explicit check.
    return a.is_multicast or not a.is_global


def check_url(url: str, resolve=socket.getaddrinfo) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise PolicyError(f"scheme not allowed: {parts.scheme or 'none'}")
    host = parts.hostname
    if not host:
        raise PolicyError("no host")
    try:
        literal = ipaddress.ip_address(host)
        addrs = [str(literal)]
    except ValueError:
        if host.lower() == "localhost":
            raise PolicyError("localhost is not allowed")
        if resolve is None:
            raise PolicyError("cannot resolve host")
        try:
            addrs = [ai[4][0] for ai in resolve(host, None)]
        except OSError as e:
            raise PolicyError(f"cannot resolve {host}: {e}")
    for ip in addrs:
        if _blocked(ip):
            raise PolicyError(f"{host} resolves to a blocked address")


def guarded(fetch, resolve=socket.getaddrinfo, max_count: int = 60, max_bytes: int = 12_000_000):
    """Wrap fetch(url) -> (final_url, bytes) into fetch(url) -> bytes under the policy."""
    state = {"count": 0, "bytes": 0}

    def wrapped(url: str) -> bytes:
        check_url(url, resolve)
        state["count"] += 1
        if state["count"] > max_count:
            raise PolicyError("too many requests")
        final_url, data = fetch(url)
        check_url(final_url, resolve)
        state["bytes"] += len(data)
        if state["bytes"] > max_bytes:
            raise PolicyError("response size cap exceeded")
        return data

    return wrapped
