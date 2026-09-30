from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.models import Event, EventType, Product, Store, Variant
from app.monitor.recorder import record_product
from tests.factories import product, variant

T0 = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
async def store(session):
    store = Store(name="Kith Canada", domain="ca.kith.com", hot_interval_s=15, sweep_interval_s=60)
    session.add(store)
    await session.flush()
    return store


async def count(session, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


async def test_first_fetch_saves_product_and_only_a_new_product_event(session, store):
    events = await record_product(session, store, product(variant("1"), variant("2")), T0)

    assert [e.type for e in events] == [EventType.NEW_PRODUCT]
    assert events[0].variant_id is None
    assert await count(session, Product) == 1
    assert await count(session, Variant) == 2


async def test_restock_is_saved_and_points_at_the_variant(session, store):
    await record_product(session, store, product(variant("1", available=False)), T0)

    later = T0 + timedelta(seconds=15)
    events = await record_product(session, store, product(variant("1", available=True)), later)

    size_1 = await session.scalar(select(Variant).where(Variant.external_id == "1"))
    assert [(e.type, e.variant_id) for e in events] == [(EventType.RESTOCK, size_1.id)]
    assert size_1.available is True
    assert size_1.updated_at == later
    assert await count(session, Event) == 2  # new_product, then restock


async def test_same_state_twice_adds_no_events_and_keeps_updated_at(session, store):
    await record_product(session, store, product(variant("1")), T0)
    events = await record_product(session, store, product(variant("1")), T0 + timedelta(minutes=1))

    size_1 = await session.scalar(select(Variant))
    saved = await session.scalar(select(Product))
    assert events == []
    assert size_1.updated_at == T0
    assert saved.last_seen_at == T0 + timedelta(minutes=1)
    assert saved.first_seen_at == T0


async def test_removed_size_is_kept_but_marked_unavailable(session, store):
    await record_product(session, store, product(variant("1"), variant("2")), T0)
    events = await record_product(session, store, product(variant("1")), T0 + timedelta(minutes=1))

    size_2 = await session.scalar(select(Variant).where(Variant.external_id == "2"))
    assert [e.type for e in events] == [EventType.SOLD_OUT]
    assert size_2.available is False

    # Fetching the same state again doesn't report the removed size a second time.
    again = await record_product(session, store, product(variant("1")), T0 + timedelta(minutes=2))
    assert again == []


async def test_same_product_id_at_two_stores_is_two_products(session, store):
    nrml = Store(name="NRML", domain="nrml.ca", hot_interval_s=15, sweep_interval_s=60)
    session.add(nrml)
    await session.flush()

    await record_product(session, store, product(variant("1")), T0)
    events = await record_product(session, nrml, product(variant("1")), T0)

    assert [e.type for e in events] == [EventType.NEW_PRODUCT]
    assert await count(session, Product) == 2
