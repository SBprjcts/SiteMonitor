from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.db.models import User, UserSession

EXPIRES = datetime(2026, 11, 1, tzinfo=UTC)


def make_user(email: str = "saif@example.com") -> User:
    return User(email=email, password_hash="$argon2id$fake-hash")


async def test_new_user_is_not_an_admin(session):
    session.add(make_user())
    await session.commit()
    session.expire_all()

    user = await session.scalar(select(User))
    assert user.is_admin is False
    assert user.created_at.tzinfo is UTC


async def test_duplicate_email_is_rejected(session):
    session.add_all([make_user(), make_user()])
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_session_round_trip(session):
    user = make_user()
    session.add_all([user, UserSession(id="token-abc", user=user, expires_at=EXPIRES)])
    await session.commit()
    user_id = user.id
    session.expire_all()

    saved = await session.get(UserSession, "token-abc")
    assert saved.user_id == user_id
    assert saved.expires_at == EXPIRES


async def test_session_must_belong_to_an_existing_user(session):
    session.add(UserSession(id="token-abc", user_id=999, expires_at=EXPIRES))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_a_user_can_have_several_sessions(session):
    user = make_user()
    session.add_all(
        [
            user,
            UserSession(id="laptop", user=user, expires_at=EXPIRES),
            UserSession(id="phone", user=user, expires_at=EXPIRES + timedelta(days=1)),
        ]
    )
    await session.commit()

    assert await session.scalar(select(func.count()).select_from(UserSession)) == 2


async def test_deleting_a_user_deletes_their_sessions(session):
    user = make_user()
    other = make_user("sary@example.com")
    session.add_all(
        [
            user,
            other,
            UserSession(id="mine", user=user, expires_at=EXPIRES),
            UserSession(id="theirs", user=other, expires_at=EXPIRES),
        ]
    )
    await session.commit()

    await session.execute(delete(User).where(User.id == user.id))
    await session.commit()

    assert list(await session.scalars(select(UserSession.id))) == ["theirs"]
