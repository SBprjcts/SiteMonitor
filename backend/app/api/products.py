from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Event, Platform, Product, Store
from app.db.session import get_session
from app.monitor.adapters.base import ProductNotFoundError, StoreAdapter
from app.monitor.adapters.shopify import ShopifyAdapter, parse_product_url
from app.monitor.http import create_http_client
from app.monitor.ratelimit import StoreBusyError
from app.monitor.recorder import record_product
from app.schemas.products import EventOut, ProductLookup, ProductOut

router = APIRouter(prefix="/products", tags=["products"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_store_adapter() -> AsyncIterator[StoreAdapter]:
    """FastAPI dependency, so tests can swap in a fake adapter.

    Uses the shared client, so the rate limiter covers lookups once it lands.
    """
    async with create_http_client() as client:
        yield ShopifyAdapter(client)


@router.post("/lookup")
async def lookup_product(
    body: ProductLookup,
    session: SessionDep,
    adapter: Annotated[StoreAdapter, Depends(get_store_adapter)],
) -> ProductOut:
    """Fetches a product from its store and saves it, so the user can pick sizes to watch.

    Only works for stores already being monitored: a new store has to go through the
    add-store probe first (POST /api/stores).
    """
    try:
        domain, handle = parse_product_url(body.url)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "That doesn't look like a Shopify product link",
        ) from None

    store = await session.scalar(select(Store).where(Store.domain == domain))
    if store is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"{domain} isn't a monitored store yet. Add it on the Stores page.",
        )
    if store.platform != Platform.SHOPIFY:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{store.name} isn't supported yet"
        )
    if not store.enabled:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{store.name} is paused, so its products aren't being monitored",
        )

    try:
        fresh = await adapter.fetch_product(domain, handle)
    except ProductNotFoundError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Couldn't find that product on {store.name}"
        ) from None
    except StoreBusyError:
        # The rate limiter is backing off from this store, so nothing was sent.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"{store.name} is limiting requests right now. Try again in a few minutes.",
        ) from None
    except httpx.HTTPStatusError as exc:
        busy = exc.response.status_code == 429
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE if busy else status.HTTP_502_BAD_GATEWAY,
            f"{store.name} is limiting requests right now. Try again in a few minutes."
            if busy
            else f"{store.name} returned an error ({exc.response.status_code})",
        ) from None
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Couldn't reach {store.name}") from None

    # A URL lookup is usually for an existing product, so it never announces new_product.
    await record_product(session, store, fresh)
    await session.commit()
    product_id = await session.scalar(
        select(Product.id).where(
            Product.store_id == store.id, Product.external_id == fresh.external_id
        )
    )
    return await _product_out(session, product_id)


@router.get("/{product_id}")
async def get_product(product_id: int, session: SessionDep) -> ProductOut:
    return await _product_out(session, product_id)


@router.get("/{product_id}/events")
async def list_product_events(
    product_id: int,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[EventOut]:
    """The product's history, newest first."""
    if await session.get(Product, product_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    events = await session.scalars(
        select(Event)
        .where(Event.product_id == product_id)
        .order_by(Event.occurred_at.desc(), Event.id.desc())
        .limit(limit)
    )
    return [EventOut.model_validate(e) for e in events]


async def _product_out(session: AsyncSession, product_id: int) -> ProductOut:
    product = await session.scalar(
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.variants), selectinload(Product.store))
        # The lookup just wrote this product in the same session; read it fresh.
        .execution_options(populate_existing=True)
    )
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return ProductOut.model_validate(product)
