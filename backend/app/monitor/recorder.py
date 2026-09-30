"""Saves a freshly fetched product and records what changed since the last fetch.

The glue between the adapter (fetch), the diff (compare), and the DB (remember).
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Event, Product, Store, Variant, utcnow
from app.monitor.adapters.base import ProductData, VariantData
from app.monitor.diff import diff_product


async def record_product(
    session: AsyncSession, store: Store, fresh: ProductData, now: datetime | None = None
) -> list[Event]:
    """Diffs `fresh` against the stored product, saves it, and returns the new events.

    Flushes but does not commit, so the caller decides when the transaction ends.
    """
    now = now or utcnow()
    product = await session.scalar(
        select(Product)
        .where(Product.store_id == store.id, Product.external_id == fresh.external_id)
        .options(selectinload(Product.variants))
    )
    changes = diff_product(_to_product_data(product) if product else None, fresh)

    if product is None:
        product = Product(store=store, external_id=fresh.external_id, first_seen_at=now)
        product.variants = []
        session.add(product)

    product.handle = fresh.handle
    product.title = fresh.title
    product.vendor = fresh.vendor
    product.image_url = fresh.image_url
    product.url = fresh.url
    product.last_seen_at = now

    variants = {v.external_id: v for v in product.variants}
    for data in fresh.variants:
        variant = variants.get(data.external_id)
        if variant is None:
            variant = Variant(external_id=data.external_id, updated_at=now)
            product.variants.append(variant)
            variants[data.external_id] = variant
        _update_variant(variant, data, now)

    # A size that vanished from the store is kept (for history) but marked unavailable.
    fresh_ids = {v.external_id for v in fresh.variants}
    for external_id, variant in variants.items():
        if external_id not in fresh_ids and variant.available:
            variant.available = False
            variant.updated_at = now

    await session.flush()  # assigns ids to new rows, which the events point at

    events = [
        Event(
            store_id=store.id,
            product_id=product.id,
            variant_id=variants[c.variant_external_id].id if c.variant_external_id else None,
            type=c.type,
            old_value=c.old_value,
            new_value=c.new_value,
            occurred_at=now,
        )
        for c in changes
    ]
    session.add_all(events)
    await session.flush()
    return events


def _update_variant(variant: Variant, data: VariantData, now: datetime) -> None:
    fields = {
        "size": data.size,
        "sku": data.sku,
        "price_cents": data.price_cents,
        "available": data.available,
    }
    if any(getattr(variant, name, None) != value for name, value in fields.items()):
        for name, value in fields.items():
            setattr(variant, name, value)
        variant.updated_at = now


def _to_product_data(product: Product) -> ProductData:
    """The stored state, in the same shape the adapter returns, so the diff can compare them."""
    return ProductData(
        external_id=product.external_id,
        handle=product.handle,
        title=product.title,
        vendor=product.vendor,
        image_url=product.image_url,
        url=product.url,
        # Not stored per product, and the diff doesn't use them.
        tags=[],
        description_html="",
        variants=[
            VariantData(
                external_id=v.external_id,
                size=v.size,
                sku=v.sku,
                price_cents=v.price_cents,
                available=v.available,
            )
            for v in product.variants
        ],
    )
