"""Compares a product's stored state with a fresh fetch and returns what changed.

Pure: no DB, no HTTP. Old and new state in, events out. See "Diff engine" in CLAUDE.md.
"""

from pydantic import BaseModel

from app.db.models import EventType
from app.monitor.adapters.base import ProductData


class EventData(BaseModel):
    type: EventType
    # Which size changed (Shopify's variant id). None for product-level events.
    variant_external_id: str | None = None
    old_value: str | None = None
    new_value: str | None = None


def diff_product(
    old: ProductData | None, new: ProductData, *, announce_new: bool = False
) -> list[EventData]:
    """Returns the events between two snapshots of the same product.

    - First sighting (old is None) is a baseline, never a burst of restocks. It emits
      new_product only if `announce_new`: seeing a product for the first time doesn't mean
      the store just added it (a store's first sweep sees ~250 existing products).
    - A size going from unavailable to available is a restock, and the reverse is sold_out.
    - A size whose price goes down is a price_drop (in cents).
    - A size that appears already in stock counts as a restock.
    - A size that disappears while in stock counts as sold_out.
    """
    if old is None:
        return [EventData(type=EventType.NEW_PRODUCT)] if announce_new else []

    events: list[EventData] = []
    old_variants = {v.external_id: v for v in old.variants}
    new_ids = {v.external_id for v in new.variants}

    for variant in new.variants:
        before = old_variants.get(variant.external_id)

        if before is None:
            if variant.available:
                events.append(_availability(EventType.RESTOCK, variant.external_id, None))
            continue

        if not before.available and variant.available:
            events.append(_availability(EventType.RESTOCK, variant.external_id, False))
        elif before.available and not variant.available:
            events.append(_availability(EventType.SOLD_OUT, variant.external_id, True))

        if variant.price_cents < before.price_cents:
            events.append(
                EventData(
                    type=EventType.PRICE_DROP,
                    variant_external_id=variant.external_id,
                    old_value=str(before.price_cents),
                    new_value=str(variant.price_cents),
                )
            )

    for external_id, before in old_variants.items():
        if external_id not in new_ids and before.available:
            events.append(_availability(EventType.SOLD_OUT, external_id, True))

    return events


def _availability(type_: EventType, external_id: str, was_available: bool | None) -> EventData:
    return EventData(
        type=type_,
        variant_external_id=external_id,
        old_value=None if was_available is None else str(was_available).lower(),
        new_value=str(type_ is EventType.RESTOCK).lower(),
    )
