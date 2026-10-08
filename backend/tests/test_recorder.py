from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

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


async def test_first_fetch_saves_a_silent_baseline(session, store):
    result = await record_product(session, store, product(variant("1"), variant("2")), T0)

    assert result.first_sighting is True
    assert result.events == []
    assert await count(session, Product) == 1
    assert await count(session, Variant) == 2


async def test_first_fetch_announced_is_one_new_product_event(session, store):
    result = await record_product(session, store, product(variant("1")), T0, announce_new=True)

    assert [(e.type, e.variant_id) for e in result.events] == [(EventType.NEW_PRODUCT, None)]


async def test_restock_is_saved_and_points_at_the_variant(session, store):
    await record_product(session, store, product(variant("1", available=False)), T0)

    later = T0 + timedelta(seconds=15)
    result = await record_product(session, store, product(variant("1", available=True)), later)

    size_1 = await session.scalar(select(Variant).where(Variant.external_id == "1"))
    assert result.first_sighting is False
    assert [(e.type, e.variant_id) for e in result.events] == [(EventType.RESTOCK, size_1.id)]
    assert size_1.available is True
    assert size_1.updated_at == later
    assert await count(session, Event) == 1


async def test_same_state_twice_adds_no_events_and_keeps_updated_at(session, store):
    await record_product(session, store, product(variant("1")), T0)
    result = await record_product(session, store, product(variant("1")), T0 + timedelta(minutes=1))

    size_1 = await session.scalar(select(Variant))
    saved = await session.scalar(select(Product))
    assert result.events == []
    assert size_1.updated_at == T0
    assert saved.last_seen_at == T0 + timedelta(minutes=1)
    assert saved.first_seen_at == T0


async def test_removed_size_is_kept_but_marked_unavailable(session, store):
    await record_product(session, store, product(variant("1"), variant("2")), T0)
    result = await record_product(session, store, product(variant("1")), T0 + timedelta(minutes=1))

    size_2 = await session.scalar(select(Variant).where(Variant.external_id == "2"))
    assert [e.type for e in result.events] == [EventType.SOLD_OUT]
    assert size_2.available is False

    # Fetching the same state again doesn't report the removed size a second time.
    again = await record_product(session, store, product(variant("1")), T0 + timedelta(minutes=2))
    assert again.events == []


async def test_search_text_is_saved_and_kept_up_to_date(session, store):
    fresh = product(variant("1"))
    await record_product(session, store, fresh, T0)

    renamed = fresh.model_copy(update={"title": "GEL-LYTE III OG"})
    await record_product(session, store, renamed, T0 + timedelta(minutes=1))

    saved = await session.scalar(select(Product))
    assert saved.search_text.startswith("gel-lyte iii og ")


async def test_same_product_id_at_two_stores_is_two_products(session, store):
    nrml = Store(name="NRML", domain="nrml.ca", hot_interval_s=15, sweep_interval_s=60)
    session.add(nrml)
    await session.flush()

    await record_product(session, store, product(variant("1")), T0)
    result = await record_product(session, nrml, product(variant("1")), T0)

    assert result.first_sighting is True
    assert await count(session, Product) == 2


async def test_size_added_later_takes_its_place_in_the_store_order(session, store):
    await record_product(session, store, product(variant("9"), variant("10")), T0)

    # The store adds a 9.5 between the two existing sizes.
    later = T0 + timedelta(minutes=1)
    await record_product(
        session, store, product(variant("9"), variant("9.5"), variant("10")), later
    )

    rows = await session.execute(select(Variant.external_id, Variant.position, Variant.updated_at))
    by_id = {external_id: (position, updated_at) for external_id, position, updated_at in rows}
    assert {k: v[0] for k, v in by_id.items()} == {"9": 0, "9.5": 1, "10": 2}
    # Moving down the list isn't a stock or price change.
    assert by_id["10"][1] == T0


async def test_removed_sizes_move_after_the_sizes_still_on_sale(session, store):
    await record_product(session, store, product(variant("9"), variant("10"), variant("11")), T0)

    # The store drops 9 and 10 and lists a new size first, reusing position 0.
    later = T0 + timedelta(minutes=1)
    await record_product(session, store, product(variant("8"), variant("11")), later)

    saved = await session.scalar(
        select(Product)
        .options(selectinload(Product.variants))
        .execution_options(populate_existing=True)
    )
    assert [(v.external_id, v.position) for v in saved.variants] == [
        ("8", 0),
        ("11", 1),
        ("9", 2),
        ("10", 3),
    ]

    # Nothing changes on the next fetch: the removed sizes keep their place at the end.
    await record_product(session, store, product(variant("8"), variant("11")), later)
    positions = await session.execute(select(Variant.external_id, Variant.position))
    assert {external_id: position for external_id, position in positions} == {
        "8": 0,
        "11": 1,
        "9": 2,
        "10": 3,
    }
