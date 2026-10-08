import os

# Set before the app is imported, so tests never touch a real .env or DB.
os.environ.setdefault("SESSION_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("MONITOR_ENABLED", "false")

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.api.deps import get_current_user  # noqa: E402
from app.db.models import Base, User  # noqa: E402
from app.db.session import create_engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
async def session():
    """A fresh in-memory database with every table, thrown away after the test."""
    # StaticPool keeps one connection, so every query sees the same in-memory DB.
    engine = create_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def user(session) -> User:
    """A regular (non-admin) account."""
    user = User(email="user@example.com", password_hash="not-a-real-hash")
    session.add(user)
    await session.commit()
    return user


@pytest.fixture
async def admin(session) -> User:
    admin = User(email="admin@example.com", password_hash="not-a-real-hash", is_admin=True)
    session.add(admin)
    await session.commit()
    return admin


def log_in_as(user: User | None) -> None:
    """Makes API requests act as `user`, skipping the cookie. None logs out.

    Call it after the test's API client fixture is set up. The override is removed when
    that fixture clears `app.dependency_overrides`.
    """
    if user is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = lambda: user
