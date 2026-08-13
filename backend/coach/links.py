"""Does the link a builder filed actually answer? One thin seam over one request.

BUILD's bar is "a link to something running" (bar.BAR), and until this module
existed nothing in the product ever opened it: the vision model reads a
screenshot, but a URL was trusted text. A pasted `https://my-app.vercel.app`
with nothing deployed behind it read exactly like a working deploy, which is the
cheapest honest proof a phone-first builder has and the one this rewards.

Optional by construction, in the same sense as `storage`: every failure here is
an ordinary state and returns `None`. Three states, not two —

    True   the link answered
    False  the server said there is nothing at that address
    None   we never got an answer, and therefore have nothing to say

`None` is the load-bearing one. A first deploy sits behind a sleeping free tier,
a password-protected preview, or a campus network as often as it sits on a
working URL, so the cost of a wrong `False` is paid by exactly the builder this
product is for. Anything ambiguous — timeout, DNS failure, refused connection,
a target we decline to fetch — resolves to silence rather than to a claim.

SECURITY. This fetches a URL a stranger typed, from a server that sits inside a
private network with a cloud metadata endpoint on it. The address is validated
before a socket is opened, redirects are never followed (a 302 to
169.254.169.254 is the same attack wearing a hat), no response body is ever
read, and one bounded timeout applies to both requests. The residual hole is
DNS rebinding: `_resolve` and the socket `requests` opens are two separate
lookups, so a name that answers publicly on the first and privately on the
second is not caught here. Closing it means pinning the connection to the
validated address, which is a custom transport adapter — filed rather than done,
because with redirects off and no body read the reachable payoff is a status
code, and a status code is what this module returns to the judge as one clause.
"""

import ipaddress
import socket
from urllib.parse import urlsplit

import requests
from django.conf import settings
from loguru import logger

# The only answers taken to mean "there is nothing at that address". Everything
# else that answers at all is a server that exists: 401 and 403 are a private
# repo, a Figma board or a password-protected preview, and a 500 is a deploy
# that is broken rather than absent. Neither is this check's business.
NOT_THERE = frozenset({404, 410})

# Hosts that refuse HEAD outright. Worth one retry, because the alternative is
# calling a live site dead over a method it never supported.
HEAD_UNSUPPORTED = frozenset({405, 501})

SCHEMES = frozenset({"http", "https"})


def _resolve(host: str) -> list[str]:
    """Every address the name answers with — all of them, because a name that
    resolves to one public and one private address must not pass on the public
    one."""
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def _public(addresses: list[str]) -> bool:
    try:
        return bool(addresses) and all(
            ipaddress.ip_address(addr).is_global for addr in addresses
        )
    except ValueError:
        return False


def _fetch(url: str, method: str) -> int:
    """One request, one status code, nothing else brought back.

    `stream=True` so the body is never downloaded on the GET retry — the answer
    this module wants is in the status line, and a proof link could point at
    anything of any size.
    """
    response = requests.request(
        method,
        url,
        timeout=settings.LINK_CHECK_TIMEOUT_S,
        allow_redirects=False,
        stream=True,
        headers={"User-Agent": settings.LINK_CHECK_USER_AGENT},
    )
    response.close()
    return response.status_code


def check(url: str) -> bool | None:
    """True answered, False nothing there, None no answer to report."""
    parts = urlsplit(url)
    if parts.scheme not in SCHEMES or not parts.hostname:
        return None
    try:
        # A literal address is checked as itself. Resolving it would be a lookup
        # that cannot change the answer, and skipping it keeps the loopback and
        # metadata cases decidable without touching a resolver at all.
        try:
            addresses = [str(ipaddress.ip_address(parts.hostname))]
        except ValueError:
            addresses = _resolve(parts.hostname)
    except OSError:
        # A name that does not resolve is the shape a made-up link often has —
        # and it is also the shape of our own DNS being down, which would mark
        # every builder's link dead at once. Unresolvable stays unchecked.
        logger.debug(f"Link check could not resolve {parts.hostname}")
        return None
    if not _public(addresses):
        logger.info(f"Link check declined a non-public target: {parts.hostname}")
        return None
    try:
        status = _fetch(url, "HEAD")
        if status in HEAD_UNSUPPORTED:
            status = _fetch(url, "GET")
    # Deliberately every exception, not requests' own tree: a bad URL, a TLS
    # failure and a socket error are one state of knowledge here, and the whole
    # point of this module is that none of them may cost the builder anything.
    except Exception as exc:
        logger.debug(f"Link check got no answer from {parts.hostname}: {exc}")
        return None
    return status not in NOT_THERE
