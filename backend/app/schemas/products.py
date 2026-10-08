from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.db.models import EventType
from app.schemas.stores import StoreOut


class VariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    size: str
    sku: str | None
    price_cents: int
    available: bool
    updated_at: datetime


class ProductOut(BaseModel):
    """A product with every size and its store. search_text stays internal."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    store_id: int
    external_id: str
    handle: str
    title: str
    vendor: str | None
    image_url: str | None
    url: str
    first_seen_at: datetime
    last_seen_at: datetime
    variants: list[VariantOut]
    store: StoreOut

    @field_validator("variants")
    @classmethod
    def _store_order(cls, variants: list[VariantOut]) -> list[VariantOut]:
        # Sizes were inserted in the store's order, so id order is the size order.
        return sorted(variants, key=lambda v: v.id)


class ProductLookup(BaseModel):
    url: str


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    store_id: int
    product_id: int
    variant_id: int | None
    type: EventType
    old_value: str | None
    new_value: str | None
    occurred_at: datetime
