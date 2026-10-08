import httpx
import pytest
from sqlalchemy import func, select

from app.db.models import Product, Store, User, Watch
from app.db.session import get_session
from app.main import app
from app.monitor.recorder import record_product
from tests.conftest import log_in_as
from tests.factories import product, variant


@pytest.fixture
async def api(session, user):
    """An API client logged in as the regular `user`."""

    async def test_session():
        yield session

    app.dependency_overrides[get_session] = test_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api") as client:
        log_in_as(user)
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def other_user(session) -> User:
    other = User(email="other@example.com", password_hash="not-a-real-hash")
    session.add(other)
    await session.commit()
    return other


@pytest.fixture
async def shoe(session) -> Product:
    """A saved product with sizes 9 (id "1"), 10 ("2", sold out), and 11 ("3")."""
    store = Store(name="NRML", domain="nrml.ca", hot_interval_s=15, sweep_interval_s=60)
    session.add(store)
    await session.flush()
    await record_product(
        session,
        store,
        product(
            variant("1", size="9"),
            variant("2", size="10", available=False),
            variant("3", size="11"),
        ),
    )
    await session.commit()
    return await session.scalar(select(Product))


def new_watch(product_id: int, **overrides) -> dict:
    return {"type": "product", "product_id": product_id, "event_types": ["restock"], **overrides}


# The fields the frontend's WatchListItem type expects (frontend/src/api/types.ts).
WATCH_FIELDS = {
    "id",
    "type",
    "product_id",
    "query",
    "keywords_pos",
    "keywords_neg",
    "store_ids",
    "sizes",
    "event_types",
    "max_price_cents",
    "webhook_id",
    "active",
    "created_at",
    "product",
}


# POST /watches


async def test_create_product_watch(api, shoe, user, session):
    response = await api.post(
        "/watches",
        json=new_watch(
            shoe.id,
            sizes=["2", "3"],
            event_types=["restock", "price_drop"],
            max_price_cents=20000,
        ),
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == WATCH_FIELDS
    assert body["sizes"] == ["2", "3"]
    assert body["event_types"] == ["restock", "price_drop"]
    assert body["max_price_cents"] == 20000
    assert body["active"] is True
    assert body["webhook_id"] is None
    assert body["product"]["title"] == "GEL-LYTE III"
    assert [v["size"] for v in body["product"]["variants"]] == ["9", "10", "11"]

    saved = await session.scalar(select(Watch))
    assert saved.user_id == user.id


async def test_create_watch_for_every_size(api, shoe):
    response = await api.post("/watches", json=new_watch(shoe.id))

    assert response.status_code == 201
    assert response.json()["sizes"] is None


async def test_duplicates_in_the_request_are_dropped(api, shoe):
    response = await api.post(
        "/watches",
        json=new_watch(shoe.id, sizes=["1", "1"], event_types=["restock", "restock"]),
    )

    assert response.json()["sizes"] == ["1"]
    assert response.json()["event_types"] == ["restock"]


async def test_create_watch_for_missing_product(api):
    response = await api.post("/watches", json=new_watch(999))

    assert response.status_code == 404


async def test_create_watch_with_unknown_size(api, shoe):
    response = await api.post("/watches", json=new_watch(shoe.id, sizes=["1", "999"]))

    assert response.status_code == 422
    assert response.json()["detail"] == "GEL-LYTE III has no size with id 999"


@pytest.mark.parametrize(
    "overrides",
    [
        {"event_types": []},
        {"event_types": ["new_product"]},  # only style-code and keyword watches
        {"event_types": ["gone"]},
        {"sizes": []},  # use null for every size
        {"max_price_cents": 0},
        {"type": "keyword"},  # slice C
    ],
)
async def test_create_watch_rejects_invalid_input(api, shoe, session, overrides):
    response = await api.post("/watches", json=new_watch(shoe.id, **overrides))

    assert response.status_code == 422
    assert await session.scalar(select(func.count()).select_from(Watch)) == 0


async def test_cannot_watch_the_same_product_twice(api, shoe):
    assert (await api.post("/watches", json=new_watch(shoe.id))).status_code == 201

    response = await api.post("/watches", json=new_watch(shoe.id, sizes=["1"]))

    assert response.status_code == 409
    assert response.json()["detail"] == "You're already watching this product"


async def test_two_users_can_watch_the_same_product(api, shoe, other_user):
    await api.post("/watches", json=new_watch(shoe.id))
    log_in_as(other_user)

    response = await api.post("/watches", json=new_watch(shoe.id))

    assert response.status_code == 201


# GET /watches


async def test_list_only_my_watches_newest_first(api, shoe, user, other_user, session):
    second = Product(
        store_id=shoe.store_id, external_id="7002", handle="other", title="Other", url="u"
    )
    session.add(second)
    await session.commit()
    first_id = (await api.post("/watches", json=new_watch(shoe.id))).json()["id"]
    second_id = (await api.post("/watches", json=new_watch(second.id))).json()["id"]
    log_in_as(other_user)
    await api.post("/watches", json=new_watch(shoe.id))
    log_in_as(user)

    response = await api.get("/watches")

    assert response.status_code == 200
    assert [w["id"] for w in response.json()] == [second_id, first_id]
    assert response.json()[1]["product"]["id"] == shoe.id


async def test_list_is_empty_for_a_new_user(api):
    response = await api.get("/watches")

    assert response.json() == []


# PATCH and DELETE /watches/{id}


async def test_pause_and_resume(api, shoe):
    watch_id = (await api.post("/watches", json=new_watch(shoe.id))).json()["id"]

    paused = await api.patch(f"/watches/{watch_id}", json={"active": False})
    assert paused.status_code == 200
    assert paused.json()["active"] is False
    assert paused.json()["product"]["id"] == shoe.id
    assert (await api.get("/watches")).json()[0]["active"] is False

    resumed = await api.patch(f"/watches/{watch_id}", json={"active": True})
    assert resumed.json()["active"] is True


async def test_delete(api, shoe, session):
    watch_id = (await api.post("/watches", json=new_watch(shoe.id))).json()["id"]

    response = await api.delete(f"/watches/{watch_id}")

    assert response.status_code == 204
    assert await session.scalar(select(func.count()).select_from(Watch)) == 0
    assert (await api.delete(f"/watches/{watch_id}")).status_code == 404


async def test_cannot_touch_someone_elses_watch(api, shoe, user, other_user, session):
    log_in_as(other_user)
    theirs = (await api.post("/watches", json=new_watch(shoe.id))).json()["id"]
    log_in_as(user)

    # A 404, not a 403, so a user can't even tell that the watch exists.
    assert (await api.patch(f"/watches/{theirs}", json={"active": False})).status_code == 404
    assert (await api.delete(f"/watches/{theirs}")).status_code == 404
    saved = await session.get(Watch, theirs)
    await session.refresh(saved)
    assert saved.active is True


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/watches"), ("post", "/watches"), ("patch", "/watches/1"), ("delete", "/watches/1")],
)
async def test_watches_need_a_login(api, method, path):
    log_in_as(None)

    response = await api.request(method, path, json={"active": True})

    assert response.status_code == 401
