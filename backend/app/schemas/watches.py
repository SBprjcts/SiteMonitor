from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import EventType, WatchType
from app.schemas.products import ProductOut

# Events a product watch can alert on. new_product belongs to style-code and keyword
# watches (slice C): a product someone already picked can't be new.
PRODUCT_WATCH_EVENTS = (EventType.RESTOCK, EventType.SOLD_OUT, EventType.PRICE_DROP)


class WatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: WatchType
    product_id: int | None
    query: str | None
    keywords_pos: list[str]
    keywords_neg: list[str]
    store_ids: list[int] | None
    sizes: list[str] | None
    event_types: list[EventType]
    max_price_cents: int | None
    # Comes with the webhooks table (slice D); always null until then.
    webhook_id: int | None = None
    active: bool
    created_at: datetime


class WatchListItem(WatchOut):
    """A watch with its product (null for style-code and keyword watches)."""

    product: ProductOut | None


class ProductWatchCreate(BaseModel):
    type: Literal[WatchType.PRODUCT]
    product_id: int
    # Variant external ids; null means every size.
    sizes: list[str] | None = Field(default=None, min_length=1)
    event_types: list[EventType] = Field(min_length=1)
    max_price_cents: int | None = Field(default=None, gt=0)

    @field_validator("event_types")
    @classmethod
    def _product_events_only(cls, value: list[EventType]) -> list[EventType]:
        if any(e not in PRODUCT_WATCH_EVENTS for e in value):
            allowed = ", ".join(PRODUCT_WATCH_EVENTS)
            raise ValueError(f"A product watch can alert on {allowed}")
        return list(dict.fromkeys(value))  # drop duplicates, keep order

    @field_validator("sizes")
    @classmethod
    def _dedupe_sizes(cls, value: list[str] | None) -> list[str] | None:
        return list(dict.fromkeys(value)) if value is not None else None


class WatchUpdate(BaseModel):
    active: bool
