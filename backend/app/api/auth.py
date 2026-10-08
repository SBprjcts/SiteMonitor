from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, SessionDep
from app.auth.passwords import hash_password, verify_password
from app.auth.sessions import COOKIE_NAME, create_session, delete_session
from app.config import get_settings
from app.db.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_TAKEN = "An account with that email already exists"


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        httponly=True,  # page scripts can't read it
        samesite="lax",  # other sites can't send it with their own requests
        secure=settings.session_cookie_secure,
        path="/",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, response: Response, session: SessionDep) -> UserOut:
    """Creates an account and logs it in."""
    if await session.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)

    user = User(email=body.email, password_hash=await hash_password(body.password))
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        # The same email registered while we were hashing the password.
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN) from None

    token = await create_session(session, user)
    await session.commit()
    _set_session_cookie(response, token)
    return UserOut.model_validate(user)


@router.post("/login")
async def login(body: LoginRequest, response: Response, session: SessionDep) -> UserOut:
    user = await session.scalar(select(User).where(User.email == body.email))
    # Checked even when the email is unknown, and with one message for both cases, so
    # the response doesn't reveal which emails have accounts.
    if not await verify_password(body.password, user.password_hash if user else None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    token = await create_session(session, user)
    await session.commit()
    _set_session_cookie(response, token)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session: SessionDep,
    token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> None:
    """Ends this browser's session. Fine to call when not logged in."""
    if token:
        await delete_session(session, token)
        await session.commit()
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    """The logged-in user. The frontend calls this on load to decide what to show."""
    return UserOut.model_validate(user)
