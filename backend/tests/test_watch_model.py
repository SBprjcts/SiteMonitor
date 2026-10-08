from datetime import UTC

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, StatementError

from app.db.models import Product, Store, User, Watch, WatchType


def make_user(email: str = "sary@example.com") -> User:
    return User(email=email, password_hash="$argon2id$fake-hash")


async def make_product(session) -> Product:
    store = Store(name="NRML", domain="nrml.ca", hot_interval_s=15, sweep_interval_s=60)
    product = Product(
        store=store,
        external_id="7001",
        handle="rugby",
        title="Rugby",
        url="https://nrml.ca/products/rugby",
    )
    session.add(product)
    await session.flush()
    return product


async def test_product_watch_defaults(session):
    user = make_user()
    product = await make_product(session)
    session.add(user)
    await session.flush()
    session.add(
        Watch(
            user_id=user.id,
            type=WatchType.PRODUCT,
            product_id=product.id,
            event_types=["restock"],
        )
    )
    await session.commit()
    session.expire_all()

    watch = await session.scalar(select(Watch))
    assert watch.active is True
    assert watch.keywords_pos == [] and watch.keywords_neg == []
    assert watch.sizes is None and watch.store_ids is None  # all sizes, all stores
    assert watch.max_price_cents is None
    assert watch.created_at.tzinfo is UTC


async def test_json_fields_round_trip(session):
    user = make_user()
    session.add(user)
    await session.flush()
    session.add(
        Watch(
            user_id=user.id,
            type=WatchType.KEYWORD,
            query="nike, low, panda, -gs",
            keywords_pos=["nike", "low", "panda"],
            keywords_neg=["gs"],
            store_ids=[1, 3],
            sizes=["41234", "41235"],
            event_types=["restock", "new_product"],
            max_price_cents=20000,
        )
    )
    await session.commit()
    session.expire_all()

    watch = await session.scalar(select(Watch))
    assert watch.keywords_pos == ["nike", "low", "panda"]
    assert watch.keywords_neg == ["gs"]
    assert watch.store_ids == [1, 3]
    assert watch.sizes == ["41234", "41235"]
    assert watch.event_types == ["restock", "new_product"]


async def test_watch_needs_an_existing_user(session):
    session.add(Watch(user_id=999, type=WatchType.KEYWORD, event_types=["restock"]))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_watch_needs_an_existing_product(session):
    user = make_user()
    session.add(user)
    await session.flush()
    session.add(
        Watch(user_id=user.id, type=WatchType.PRODUCT, product_id=999, event_types=["restock"])
    )
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_unknown_watch_type_is_rejected(session):
    user = make_user()
    session.add(user)
    await session.flush()
    session.add(Watch(user_id=user.id, type="brand", event_types=["restock"]))
    with pytest.raises(StatementError):
        await session.commit()


async def test_deleting_a_user_deletes_only_their_watches(session):
    me, other = make_user(), make_user("saif@example.com")
    session.add_all([me, other])
    await session.flush()
    session.add_all(
        [
            Watch(user_id=me.id, type=WatchType.KEYWORD, query="mine", event_types=["restock"]),
            Watch(
                user_id=other.id, type=WatchType.KEYWORD, query="theirs", event_types=["restock"]
            ),
        ]
    )
    await session.commit()

    await session.execute(delete(User).where(User.id == me.id))
    await session.commit()

    assert list(await session.scalars(select(Watch.query))) == ["theirs"]
