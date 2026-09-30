from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, StatementError

from app.db.models import Event, EventType, Product, Store, StoreStatus, Variant


def make_store(**overrides) -> Store:
    fields = {"name": "Kith Canada", "domain": "ca.kith.com", "hot_interval_s": 15}
    return Store(**{"sweep_interval_s": 60, **fields, **overrides})


def make_product(store: Store, **overrides) -> Product:
    fields = {
        "store": store,
        "external_id": "7412345678901",
        "handle": "gel-lyte-iii",
        "title": "GEL-LYTE III",
        "url": "https://ca.kith.com/products/gel-lyte-iii",
    }
    return Product(**{**fields, **overrides})


async def test_product_with_variants_and_event_round_trip(session):
    store = make_store()
    product = make_product(store)
    variant = Variant(
        product=product, external_id="41234", size="10.5", price_cents=26000, available=True
    )
    session.add_all([store, product, variant])
    await session.flush()
    session.add(
        Event(
            store_id=store.id,
            product_id=product.id,
            variant_id=variant.id,
            type=EventType.RESTOCK,
            old_value="false",
            new_value="true",
        )
    )
    await session.commit()

    event = await session.scalar(select(Event))
    assert event.type is EventType.RESTOCK
    assert store.status is StoreStatus.OK  # default
    assert product.variants[0].price_cents == 26000


async def test_timestamps_come_back_as_utc(session):
    toronto = timezone(timedelta(hours=-4))
    store = make_store(last_ok_at=datetime(2026, 9, 28, 20, 0, tzinfo=toronto))
    session.add(store)
    await session.commit()
    session.expire_all()

    loaded = await session.scalar(select(Store))
    assert loaded.last_ok_at == datetime(2026, 9, 29, 0, 0, tzinfo=UTC)
    assert loaded.last_ok_at.tzinfo is UTC


async def test_naive_timestamps_are_rejected(session):
    session.add(make_store(last_ok_at=datetime(2026, 9, 28, 20, 0)))
    with pytest.raises(StatementError):
        await session.commit()


async def test_same_product_twice_in_one_store_is_rejected(session):
    store = make_store()
    session.add_all([make_product(store), make_product(store)])
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_same_product_id_in_two_stores_is_allowed(session):
    kith = make_store()
    nrml = make_store(name="NRML", domain="nrml.ca")
    session.add_all([make_product(kith), make_product(nrml)])
    await session.commit()


async def test_duplicate_store_domain_is_rejected(session):
    session.add_all([make_store(), make_store(name="Kith again")])
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_variant_must_belong_to_an_existing_product(session):
    session.add(Variant(product_id=999, external_id="1", size="9", price_cents=1, available=True))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_invalid_event_type_is_rejected(session):
    store = make_store()
    product = make_product(store)
    session.add_all([store, product])
    await session.flush()
    session.add(Event(store_id=store.id, product_id=product.id, type="exploded"))
    with pytest.raises(StatementError):
        await session.commit()
