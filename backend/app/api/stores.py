from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser
from app.config import get_settings
from app.db.models import Platform, Store
from app.db.session import get_session
from app.schemas.stores import StoreCreate, StoreOut, StoreUpdate
from app.stores.probe import StoreProbe, get_store_probe

router = APIRouter(prefix="/stores", tags=["stores"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("")
async def list_stores(session: SessionDep) -> list[StoreOut]:
    stores = await session.scalars(select(Store).order_by(Store.id))
    return [StoreOut.model_validate(store) for store in stores]


@router.patch("/{store_id}")
async def update_store(
    store_id: int, body: StoreUpdate, session: SessionDep, _admin: AdminUser
) -> StoreOut:
    """Enables or disables a store. Admins only: stores are shared by every user."""
    store = await session.get(Store, store_id)
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found")
    if body.enabled and store.platform != Platform.SHOPIFY:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{store.name} isn't supported yet"
        )

    store.enabled = body.enabled
    await session.commit()
    return StoreOut.model_validate(store)


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_store(
    body: StoreCreate,
    session: SessionDep,
    probe: Annotated[StoreProbe, Depends(get_store_probe)],
) -> StoreOut:
    already_added = f"{body.domain} is already being monitored"
    if await session.scalar(select(Store.id).where(Store.domain == body.domain)):
        raise HTTPException(status.HTTP_409_CONFLICT, already_added)

    if not await probe(body.domain):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Couldn't find a Shopify product feed at {body.domain}",
        )

    settings = get_settings()
    store = Store(
        name=body.name or body.domain,
        domain=body.domain,
        hot_interval_s=settings.default_hot_interval_s,
        sweep_interval_s=settings.default_sweep_interval_s,
    )
    session.add(store)
    try:
        await session.commit()
    except IntegrityError:
        # Someone added the same domain while we were probing it.
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, already_added) from None
    await session.refresh(store)
    return StoreOut.model_validate(store)
