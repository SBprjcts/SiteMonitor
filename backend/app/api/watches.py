"""The logged-in user's watches. Every query filters by user.id (see Rules in CLAUDE.md)."""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.db.models import Product, User, Watch, WatchType
from app.schemas.products import ProductOut
from app.schemas.watches import ProductWatchCreate, WatchListItem, WatchOut, WatchUpdate

router = APIRouter(prefix="/watches", tags=["watches"])


@router.get("")
async def list_watches(user: CurrentUser, session: SessionDep) -> list[WatchListItem]:
    """The user's watches, newest first, each with its product."""
    watches = (
        await session.scalars(
            select(Watch)
            .where(Watch.user_id == user.id)
            .order_by(Watch.created_at.desc(), Watch.id.desc())
        )
    ).all()
    products = await _products_by_id(session, {w.product_id for w in watches if w.product_id})
    return [_list_item(w, products.get(w.product_id)) for w in watches]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_watch(
    body: ProductWatchCreate, user: CurrentUser, session: SessionDep
) -> WatchListItem:
    """Watches a product the user looked up (POST /api/products/lookup)."""
    product = (await _products_by_id(session, {body.product_id})).get(body.product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")

    if body.sizes is not None:
        known = {v.external_id for v in product.variants}
        if unknown := [s for s in body.sizes if s not in known]:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{product.title} has no size with id {unknown[0]}",
            )

    already = await session.scalar(
        select(Watch.id).where(Watch.user_id == user.id, Watch.product_id == product.id)
    )
    if already:
        raise HTTPException(status.HTTP_409_CONFLICT, "You're already watching this product")

    watch = Watch(
        user_id=user.id,
        type=WatchType.PRODUCT,
        product_id=product.id,
        sizes=body.sizes,
        event_types=[e.value for e in body.event_types],
        max_price_cents=body.max_price_cents,
    )
    session.add(watch)
    await session.commit()
    await session.refresh(watch)
    return _list_item(watch, product)


@router.patch("/{watch_id}")
async def update_watch(
    watch_id: int, body: WatchUpdate, user: CurrentUser, session: SessionDep
) -> WatchListItem:
    """Pauses or resumes a watch."""
    watch = await _own_watch(session, user, watch_id)
    watch.active = body.active
    await session.commit()
    products = await _products_by_id(session, {watch.product_id} if watch.product_id else set())
    return _list_item(watch, products.get(watch.product_id))


@router.delete("/{watch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watch(watch_id: int, user: CurrentUser, session: SessionDep) -> Response:
    watch = await _own_watch(session, user, watch_id)
    await session.delete(watch)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _own_watch(session: AsyncSession, user: User, watch_id: int) -> Watch:
    """The user's watch, or 404. Someone else's watch is a 404 too, so ids don't leak."""
    watch = await session.scalar(
        select(Watch).where(Watch.id == watch_id, Watch.user_id == user.id)
    )
    if watch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Watch not found")
    return watch


async def _products_by_id(session: AsyncSession, ids: set[int]) -> dict[int, ProductOut]:
    if not ids:
        return {}
    products = await session.scalars(
        select(Product)
        .where(Product.id.in_(ids))
        .options(selectinload(Product.variants), selectinload(Product.store))
    )
    return {p.id: ProductOut.model_validate(p) for p in products}


# Columns copied from a Watch row into the response (webhook_id has no column yet).
_WATCH_FIELDS = [name for name in WatchOut.model_fields if name != "webhook_id"]


def _list_item(watch: Watch, product: ProductOut | None) -> WatchListItem:
    return WatchListItem(**{name: getattr(watch, name) for name in _WATCH_FIELDS}, product=product)
