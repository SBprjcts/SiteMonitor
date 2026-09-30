"""Runs the monitor on its own, without the API.

Phase 1 only has a one-shot check:
    uv run python -m app.monitor --once https://ca.kith.com/products/<handle>

The first run saves a baseline; later runs print what changed since the previous run.
The polling loops (phase 2) will run here when --once is left out.
"""

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Event, EventType, Store, Variant
from app.db.session import SessionLocal, engine
from app.monitor.adapters.base import ProductNotFoundError, StoreAdapter
from app.monitor.adapters.shopify import ShopifyAdapter, parse_product_url
from app.monitor.http import create_http_client
from app.monitor.recorder import record_product


async def run_once(session: AsyncSession, adapter: StoreAdapter, url: str) -> list[str]:
    """Fetches one product, records it, commits, and returns the report lines to print."""
    domain, handle = parse_product_url(url)
    store = await session.scalar(select(Store).where(Store.domain == domain))
    lines = []
    if store is None:
        settings = get_settings()
        store = Store(
            name=domain,
            domain=domain,
            hot_interval_s=settings.default_hot_interval_s,
            sweep_interval_s=settings.default_sweep_interval_s,
        )
        session.add(store)
        lines.append(f"(added {domain} as a new store)")

    fresh = await adapter.fetch_product(domain, handle)
    events = await record_product(session, store, fresh)
    await session.commit()

    lines.append(f"{fresh.title}  [{store.name}]")
    for v in fresh.variants:
        stock = "in stock" if v.available else "sold out"
        lines.append(f"  {v.size:<12} {stock:<10} ${v.price_cents / 100:.2f}")
    lines.append("")
    lines.extend(await _describe(session, events))
    return lines


async def _describe(session: AsyncSession, events: list[Event]) -> list[str]:
    if not events:
        return ["No changes since the last run."]
    if events[0].type is EventType.NEW_PRODUCT:
        return ["First time seeing this product: saved a baseline. Run again later."]

    variant_ids = [e.variant_id for e in events]
    rows = await session.execute(
        select(Variant.id, Variant.size).where(Variant.id.in_(variant_ids))
    )
    sizes = {variant_id: size for variant_id, size in rows}
    lines = ["Changes since the last run:"]
    for e in events:
        detail = ""
        if e.type is EventType.PRICE_DROP:
            detail = f"  ${int(e.old_value) / 100:.2f} -> ${int(e.new_value) / 100:.2f}"
        lines.append(f"  {e.type.value.upper():<11} {sizes[e.variant_id]}{detail}")
    return lines


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.monitor", description=__doc__.split("\n")[0]
    )
    parser.add_argument("--once", metavar="PRODUCT_URL", help="check one product and exit")
    args = parser.parse_args(argv)

    if not args.once:
        parser.error("the polling loops arrive in phase 2; use --once PRODUCT_URL for now")

    try:
        async with create_http_client() as client, SessionLocal() as session:
            for line in await run_once(session, ShopifyAdapter(client), args.once):
                print(line)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ProductNotFoundError as exc:
        print(f"error: product not found: {exc}", file=sys.stderr)
        return 1
    except OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        print(
            "error: the database has no tables yet. Run: uv run alembic upgrade head",
            file=sys.stderr,
        )
        return 1
    finally:
        await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
