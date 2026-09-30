"""Checks that a domain is a Shopify store we can monitor, before it is added.

This is a single request made when a user adds a store, so it doesn't go through the
per-domain rate limiter yet. Switch it to the Shopify adapter once the engine lands.
"""

from collections.abc import Awaitable, Callable

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

StoreProbe = Callable[[str], Awaitable[bool]]


async def probe_shopify_store(domain: str) -> bool:
    """True if the domain serves a non-empty Shopify products.json.

    An empty product list counts as a failure: headless (Hydrogen) Shopify stores such as
    Haven return `{"products": []}`, and the Shopify adapter can't monitor them.
    """
    try:
        async with httpx.AsyncClient(
            timeout=10, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
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


def get_store_probe() -> StoreProbe:
    """FastAPI dependency, so tests can swap in a fake probe."""
    return probe_shopify_store
