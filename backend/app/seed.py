"""Seeds the store list from CLAUDE.md. Safe to run repeatedly.

Usage (after `uv run alembic upgrade head`):
    uv run python -m app.seed
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Store
from app.db.session import SessionLocal, engine

# (name, domain). All verified to serve products.json on 2026-09-28.
STORES = [
    ("Kith Canada", "ca.kith.com"),
    ("Momentum", "momentumshop.ca"),
    ("NRML", "nrml.ca"),
    ("Foosh", "foosh.ca"),
    ("Qlassic", "qlassic.ca"),
    ("Courtside Sneakers", "courtsidesneakers.com"),
    ("Sneakerbox", "sneakerboxshop.ca"),
    ("Lessoneseven", "lessoneseven.com"),
    ("Solestop", "solestop.com"),
    ("JD Sports Canada", "jdsports.ca"),
    ("Livestock", "deadstock.ca"),
    ("BB Branded", "bbbranded.com"),
]


async def seed_stores(session: AsyncSession) -> int:
    """Adds any seeded store that isn't in the DB yet. Returns how many were added."""
    settings = get_settings()
    existing = set(await session.scalars(select(Store.domain)))
    new_stores = [
        Store(
            name=name,
            domain=domain,
            hot_interval_s=settings.default_hot_interval_s,
            sweep_interval_s=settings.default_sweep_interval_s,
        )
        for name, domain in STORES
        if domain not in existing
    ]
    session.add_all(new_stores)
    await session.commit()
    return len(new_stores)


async def main() -> None:
    async with SessionLocal() as session:
        added = await seed_stores(session)
    await engine.dispose()
    print(f"Seeded {added} new store(s); {len(STORES) - added} already existed.")


if __name__ == "__main__":
    asyncio.run(main())
