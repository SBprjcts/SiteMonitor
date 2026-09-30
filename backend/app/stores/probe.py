"""Checks that a domain is a Shopify store we can monitor, before it is added.

This is a single request made when a user adds a store, so it doesn't go through the
per-domain rate limiter.

The domain comes from user input, so the probe only talks to public addresses: otherwise
someone could make the server call 127.0.0.1 or a cloud metadata IP. Every request is
checked, including redirects.
"""

import asyncio
import socket
from collections.abc import Awaitable, Callable
from ipaddress import ip_address

import httpx

from app.monitor.http import create_http_client

StoreProbe = Callable[[str], Awaitable[bool]]


class NonPublicHostError(httpx.RequestError):
    """The request would reach a private, loopback, or otherwise non-public address."""


async def probe_shopify_store(domain: str) -> bool:
    """True if the domain serves a non-empty Shopify products.json.

    An empty product list counts as a failure: headless (Hydrogen) Shopify stores such as
    Haven return `{"products": []}`, and the Shopify adapter can't monitor them.
    """
    try:
        async with create_http_client() as client:
            client.event_hooks = {"request": [_reject_non_public_host]}
            response = await client.get(f"https://{domain}/products.json", params={"limit": 1})
    except httpx.HTTPError:
        return False

    if response.status_code != 200:
        return False
    try:
        data = response.json()
    except ValueError:
        return False
    return isinstance(data, dict) and bool(data.get("products"))


async def _reject_non_public_host(request: httpx.Request) -> None:
    if not await is_public_host(request.url.host):
        raise NonPublicHostError(f"{request.url.host} is not a public address", request=request)


async def is_public_host(host: str) -> bool:
    """True only if every address the host resolves to is on the public internet."""
    try:
        addresses = [ip_address(host)]
    except ValueError:
        try:
            # IPv6 link-local results carry a zone ("fe80::1%12"), which ip_address rejects.
            addresses = [ip_address(a.split("%")[0]) for a in await resolve_host(host)]
        except (OSError, ValueError):
            return False
    return bool(addresses) and all(a.is_global for a in addresses)


async def resolve_host(host: str) -> list[str]:
    """The IP addresses a hostname resolves to. Tests replace this to avoid real DNS."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def get_store_probe() -> StoreProbe:
    """FastAPI dependency, so tests can swap in a fake probe."""
    return probe_shopify_store
