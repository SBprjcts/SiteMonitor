from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.auth.passwords import hash_password
from app.auth.sessions import COOKIE_NAME
from app.db.models import Store, User, UserSession, utcnow
from app.db.session import get_session
from app.main import app
from app.make_admin import set_admin
from app.stores.probe import get_store_probe
from tests.conftest import log_in_as

PASSWORD = "correct horse battery"


@pytest.fixture
async def api(session):
    """An API client on the test database. Nothing is logged in: cookies are the real thing."""

    async def test_session():
        yield session

    async def probe(domain: str) -> bool:
        return True

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_store_probe] = lambda: probe
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api") as client:
        yield client
    app.dependency_overrides.clear()


async def register(api, email="saif@example.com", password=PASSWORD):
    return await api.post("/auth/register", json={"email": email, "password": password})


# Register


async def test_register_creates_a_user_and_logs_them_in(api, session):
    response = await register(api, email="  Saif@Example.com ")

    assert response.status_code == 201
    assert response.json() == {"id": 1, "email": "saif@example.com", "is_admin": False}
    assert (await api.get("/auth/me")).json()["email"] == "saif@example.com"

    saved = await session.scalar(select(User))
    assert saved.password_hash.startswith("$argon2")
    assert PASSWORD not in saved.password_hash


async def test_register_rejects_an_email_that_is_taken_whatever_the_case(api):
    await register(api)

    response = await register(api, email="SAIF@example.com")

    assert response.status_code == 409
    assert response.json()["detail"] == "An account with that email already exists"


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "saif@example.com", "password": "short"},
        {"email": "saif@example.com", "password": "x" * 129},
        {"email": "not-an-email", "password": PASSWORD},
        {"email": "saif@example.com"},
    ],
)
async def test_register_rejects_bad_input(api, session, payload):
    response = await api.post("/auth/register", json=payload)

    assert response.status_code == 422
    assert await session.scalar(select(func.count()).select_from(User)) == 0


# Login


async def test_login_sets_a_cookie_that_page_scripts_cannot_read(api):
    await register(api)
    api.cookies.clear()

    response = await api.post(
        "/auth/login", json={"email": "Saif@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith(f"{COOKIE_NAME}=")
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert (await api.get("/auth/me")).status_code == 200


async def test_wrong_password_and_unknown_email_look_the_same(api):
    await register(api)
    api.cookies.clear()

    wrong_password = await api.post(
        "/auth/login", json={"email": "saif@example.com", "password": "not the password"}
    )
    unknown_email = await api.post(
        "/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert (
        wrong_password.json() == unknown_email.json() == {"detail": "Incorrect email or password"}
    )
    assert "set-cookie" not in wrong_password.headers


async def test_the_database_never_stores_the_cookie_token(api, session):
    response = await register(api)

    token = response.cookies[COOKIE_NAME]
    stored_id = await session.scalar(select(UserSession.id))
    assert token not in stored_id
    assert len(stored_id) == 64


async def test_logging_in_clears_that_users_expired_sessions(api, session):
    await register(api)
    session.add(UserSession(id="old", user_id=1, expires_at=utcnow() - timedelta(days=1)))
    await session.commit()

    await api.post("/auth/login", json={"email": "saif@example.com", "password": PASSWORD})

    ids = list(await session.scalars(select(UserSession.id)))
    assert "old" not in ids
    assert len(ids) == 2  # the register session and the new login


# Sessions


async def test_me_requires_a_login(api):
    response = await api.get("/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Log in to continue"}


async def test_a_made_up_cookie_is_not_a_login(api):
    api.cookies.set(COOKIE_NAME, "made-up-token")

    assert (await api.get("/auth/me")).status_code == 401


async def test_an_expired_session_is_not_a_login(api, session):
    await register(api)
    saved = await session.scalar(select(UserSession))
    saved.expires_at = utcnow() - timedelta(seconds=1)
    await session.commit()

    assert (await api.get("/auth/me")).status_code == 401


async def test_logout_ends_the_session_even_if_the_cookie_is_replayed(api, session):
    token = (await register(api)).cookies[COOKIE_NAME]

    response = await api.post("/auth/logout")

    assert response.status_code == 204
    assert await session.scalar(select(func.count()).select_from(UserSession)) == 0
    api.cookies.set(COOKIE_NAME, token)  # someone kept a copy of the old cookie
    assert (await api.get("/auth/me")).status_code == 401


async def test_logout_without_a_login_is_fine(api):
    assert (await api.post("/auth/logout")).status_code == 204


async def test_logging_out_one_browser_keeps_the_other_logged_in(api, session):
    laptop = (await register(api)).cookies[COOKIE_NAME]
    api.cookies.clear()
    await api.post("/auth/login", json={"email": "saif@example.com", "password": PASSWORD})

    await api.post("/auth/logout")  # the second browser

    api.cookies.set(COOKIE_NAME, laptop)
    assert (await api.get("/auth/me")).status_code == 200


# Who can do what


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/stores"),
        ("POST", "/stores"),
        ("PATCH", "/stores/1"),
        ("POST", "/products/lookup"),
        ("GET", "/products/1"),
        ("GET", "/products/1/events"),
    ],
)
async def test_everything_but_auth_and_health_requires_a_login(api, method, path):
    response = await api.request(method, path, json={})

    assert response.status_code == 401


async def test_health_stays_public(api):
    assert (await api.get("/health")).status_code == 200


async def test_a_regular_user_can_list_and_add_stores_but_not_toggle_them(api, session, user):
    session.add(Store(name="NRML", domain="nrml.ca", hot_interval_s=15, sweep_interval_s=60))
    await session.commit()
    log_in_as(user)

    assert (await api.get("/stores")).status_code == 200
    assert (await api.post("/stores", json={"domain": "foosh.ca"})).status_code == 201

    response = await api.patch("/stores/1", json={"enabled": False})
    assert response.status_code == 403
    assert response.json() == {"detail": "Only an admin can do that"}
    assert (await session.get(Store, 1)).enabled is True


async def test_an_admin_can_toggle_a_store(api, session, admin):
    session.add(Store(name="NRML", domain="nrml.ca", hot_interval_s=15, sweep_interval_s=60))
    await session.commit()
    log_in_as(admin)

    response = await api.patch("/stores/1", json={"enabled": False})

    assert response.status_code == 200
    assert response.json()["enabled"] is False


# make_admin


async def test_make_admin_grants_and_revokes(session):
    session.add(User(email="saif@example.com", password_hash=await hash_password(PASSWORD)))
    await session.commit()

    assert await set_admin(session, " Saif@Example.com ", True) is True
    assert (await session.scalar(select(User))).is_admin is True

    assert await set_admin(session, "saif@example.com", False) is True
    assert (await session.scalar(select(User))).is_admin is False

    assert await set_admin(session, "nobody@example.com", True) is False
