from sqlalchemy import func, select

from app.config import get_settings
from app.db.models import Store
from app.seed import STORES, seed_stores


async def test_seed_adds_every_store_once(session):
    assert await seed_stores(session) == len(STORES)
    assert await seed_stores(session) == 0  # running again adds nothing

    count = await session.scalar(select(func.count()).select_from(Store))
    assert count == len(STORES)


async def test_seed_uses_default_intervals(session):
    await seed_stores(session)

    settings = get_settings()
    kith = await session.scalar(select(Store).where(Store.domain == "ca.kith.com"))
    assert kith.hot_interval_s == settings.default_hot_interval_s
    assert kith.sweep_interval_s == settings.default_sweep_interval_s
