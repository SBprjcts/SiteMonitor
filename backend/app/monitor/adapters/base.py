"""The shape every store adapter returns, whatever the store's own JSON looks like.

Adapters know nothing about the DB. The diff engine compares these objects.
"""

from typing import Protocol

from pydantic import BaseModel


class VariantData(BaseModel):
    """One size of a product."""

    external_id: str
    size: str
    sku: str | None
    price_cents: int
    available: bool


class ProductData(BaseModel):
    external_id: str
    handle: str
    title: str
    vendor: str | None
    image_url: str | None
    url: str
    tags: list[str]
    description_html: str
    variants: list[VariantData]


class ProductNotFoundError(Exception):
    """The store has no product with this handle (removed, or a typo in the URL)."""


class StoreAdapter(Protocol):
    async def fetch_product(self, domain: str, handle: str) -> ProductData: ...

    async def fetch_catalog_page(self, domain: str, page: int) -> list[ProductData]: ...
