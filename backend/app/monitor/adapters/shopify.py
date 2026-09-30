"""Reads Shopify's public JSON endpoints and normalizes them into ProductData.

Shopify serves the same product in two shapes:

| | /products/{handle}.js | /products.json |
|---|---|---|
| price | int cents (21000) | dollar string ("210.00") |
| description | description | body_html |
| image | featured_image ("//cdn...") | images[0].src |

Everything that differs is handled here, so nothing else needs to know.
"""

from decimal import Decimal
from typing import Any

import httpx

from app.monitor.adapters.base import ProductData, ProductNotFoundError, VariantData

CATALOG_PAGE_SIZE = 250  # Shopify's maximum


class ShopifyAdapter:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def fetch_product(self, domain: str, handle: str) -> ProductData:
        """One product with every size. Used by the hot loop."""
        response = await self.client.get(f"https://{domain}/products/{handle}.js")
        if response.status_code == 404:
            raise ProductNotFoundError(f"{domain}/products/{handle}")
        response.raise_for_status()
        return parse_product_js(response.json(), domain)

    async def fetch_catalog_page(self, domain: str, page: int) -> list[ProductData]:
        """Up to 250 products, most recently updated first. Empty past the last page."""
        response = await self.client.get(
            f"https://{domain}/products.json",
            params={"limit": CATALOG_PAGE_SIZE, "page": page},
        )
        response.raise_for_status()
        return [parse_catalog_product(p, domain) for p in response.json()["products"]]


def parse_product_js(data: dict[str, Any], domain: str) -> ProductData:
    """Parses /products/{handle}.js, where prices are integer cents."""
    size_key = _size_option_key(data["options"])
    return ProductData(
        external_id=str(data["id"]),
        handle=data["handle"],
        title=data["title"],
        vendor=data.get("vendor"),
        image_url=_absolute_url(data.get("featured_image")),
        url=f"https://{domain}/products/{data['handle']}",
        tags=_tags(data.get("tags")),
        description_html=data.get("description") or "",
        variants=[
            VariantData(
                external_id=str(v["id"]),
                size=_size(v, size_key),
                sku=v.get("sku") or None,
                price_cents=int(v["price"]),
                available=v["available"],
            )
            for v in data["variants"]
        ],
    )


def parse_catalog_product(data: dict[str, Any], domain: str) -> ProductData:
    """Parses one product from /products.json, where prices are dollar strings."""
    size_key = _size_option_key(data["options"])
    images = data.get("images") or []
    return ProductData(
        external_id=str(data["id"]),
        handle=data["handle"],
        title=data["title"],
        vendor=data.get("vendor"),
        image_url=images[0]["src"] if images else None,
        url=f"https://{domain}/products/{data['handle']}",
        tags=_tags(data.get("tags")),
        description_html=data.get("body_html") or "",
        variants=[
            VariantData(
                external_id=str(v["id"]),
                size=_size(v, size_key),
                sku=v.get("sku") or None,
                price_cents=dollars_to_cents(v["price"]),
                available=v["available"],
            )
            for v in data["variants"]
        ],
    )


def dollars_to_cents(price: str) -> int:
    """ "210.00" -> 21000. Decimal avoids float rounding (19.99 * 100 = 1998.9999...)."""
    return int(Decimal(price) * 100)


def _size_option_key(options: list[dict[str, Any]]) -> str | None:
    """Which variant field holds the size: "option1", "option2", or "option3".

    Stores order options differently: Kith has [Size], JD Sports has [Color, Size],
    and NRML has [SIZE, COLOR, STYLE]. So look for the option named like "size".
    """
    for index, option in enumerate(options, start=1):
        if "size" in option["name"].lower():
            return f"option{index}"
    if len(options) == 1:
        return "option1"
    return None


def _size(variant: dict[str, Any], size_key: str | None) -> str:
    size = variant.get(size_key) if size_key else None
    size = size or variant["title"]
    # Products without options (a bag, a hat) get a single "Default Title" variant.
    return "One Size" if size == "Default Title" else size


def _tags(tags: list[str] | str | None) -> list[str]:
    # Current Shopify returns a list; older themes return one comma-separated string.
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    return tags or []


def _absolute_url(url: str | None) -> str | None:
    # The .js endpoint returns protocol-relative image URLs ("//cdn.shopify.com/...").
    if url and url.startswith("//"):
        return f"https:{url}"
    return url
