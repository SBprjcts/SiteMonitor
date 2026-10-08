"""Shared FastAPI dependencies: the DB session, the logged-in user, and the admin check.

    async def my_endpoint(user: CurrentUser, session: SessionDep): ...   # must be logged in
    async def admin_endpoint(admin: AdminUser): ...                      # must be an admin

Every user-owned query must filter by `user.id` (see Rules in CLAUDE.md).
"""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import COOKIE_NAME, get_user_for_token
from app.db.models import User
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> User:
    """The logged-in user, from the session cookie. 401 if there isn't one."""
    user = await get_user_for_token(session, token) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Log in to continue")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    """403 unless the logged-in user is an admin."""
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin can do that")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
