"""Login sessions: a random token in the browser's cookie, and a row in `sessions`.

The DB stores an HMAC of the token, not the token itself, so a leaked database can't be
used to log in as anyone.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import User, UserSession, utcnow

COOKIE_NAME = "session"


def _session_id(token: str) -> str:
    """What is stored as sessions.id for a cookie token (64 hex characters)."""
    secret = get_settings().session_secret.encode()
    return hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()


async def create_session(session: AsyncSession, user: User) -> str:
    """Logs the user in. Returns the token to put in the cookie."""
    now = utcnow()
    # Tidy up this user's expired logins while we're here.
    await session.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= now)
    )
    token = secrets.token_urlsafe(32)
    session.add(
        UserSession(
            id=_session_id(token),
            user_id=user.id,
            expires_at=now + timedelta(days=get_settings().session_ttl_days),
        )
    )
    return token


async def get_user_for_token(session: AsyncSession, token: str) -> User | None:
    """The logged-in user for a cookie token, or None if it's unknown or expired."""
    return await session.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.id == _session_id(token), UserSession.expires_at > utcnow())
    )


async def delete_session(session: AsyncSession, token: str) -> None:
    await session.execute(delete(UserSession).where(UserSession.id == _session_id(token)))
