import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import func, select

from app.api.products import get_store_adapter
from app.db.models import Event, EventType, Platform, Product, Store
from app.db.session import get_session
from app.main import app
from app.monitor.adapters.base import ProductNotFoundError
from app.monitor.adapters.shopify import ShopifyAdapter
from app.monitor.recorder import record_product
from tests.conftest import log_in_as
from tests.factories import product, variant

FIXTURES = Path(__file__).parent / "fixtures" / "shopify"


class FakeAdapter:
    """Returns a prepared product (or raises) instead of calling a store."""

    def __init__(self) -> None:
        self.product = product(variant("1", size="9"), variant("2", size="10", available=False))
        self.error: Exception | None = None
        self.calls: list[tuple[str, str]] = []

    async def fetch_product(self, domain: str, handle: str):
        self.calls.append((domain, handle))
        if self.error:
            raise self.error
        return self.product

    async def fetch_catalog_page(self, domain: str, page: int):
        raise AssertionError("lookups never fetch the catalog")


@pytest.fixture
def adapter():
    return FakeAdapter()


@pytest.fixture
async def api(session, adapter, admin):
    async def test_session():
        yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_store_adapter] = lambda: adapter
    log_in_as(admin)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api") as client:
        yield client
    app.dependency_overrides.clear()


def make_store(**overrides) -> Store:
    fields = {"name": "Kith Canada", "domain": "ca.kith.com"}
    return Store(**{"hot_interval_s": 15, "sweep_interval_s": 60, **fields, **overrides})


@pytest.fixture
async def kith(session):
    store = make_store()
    session.add(store)
    await session.commit()
    return store


URL = "https://ca.kith.com/collections/footwear/products/gel-lyte-iii?variant=1"

# The fields the frontend's ProductDetail type expects (frontend/src/api/types.ts).
PRODUCT_FIELDS = {
    "id",
    "store_id",
    "external_id",
    "handle",
    "title",
    "vendor",
    "image_url",
    "url",
    "first_seen_at",
    "last_seen_at",
    "variants",
    "store",
}


# POST /products/lookup


async def test_lookup_saves_product_and_returns_sizes(api, kith, adapter, session):
    response = await api.post("/products/lookup", json={"url": URL})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == PRODUCT_FIELDS
    assert body["title"] == "GEL-LYTE III"
    assert body["store"]["domain"] == "ca.kith.com"
    assert [(v["size"], v["available"]) for v in body["variants"]] == [("9", True), ("10", False)]
    assert adapter.calls == [("ca.kith.com", "gel-lyte-iii")]
    assert await session.scalar(select(func.count()).select_from(Product)) == 1


async def test_lookup_never_announces_new_product(api, kith, session):
    await api.post("/products/lookup", json={"url": URL})

    events = (await session.scalars(select(Event))).all()
    assert events == []  # a first sighting is a silent baseline


async def test_second_lookup_updates_and_records_changes(api, kith, adapter, session):
    await api.post("/products/lookup", json={"url": URL})
    adapter.product = product(variant("1", size="9"), variant("2", size="10", available=True))

    response = await api.post("/products/lookup", json={"url": URL})

    assert response.json()["variants"][1]["available"] is True
    assert await session.scalar(select(func.count()).select_from(Product)) == 1
    events = (await session.scalars(select(Event))).all()
    assert [e.type for e in events] == [EventType.RESTOCK]


async def test_lookup_matches_store_with_www(api, kith, adapter):
    response = await api.post("/products/lookup", json={"url": "www.ca.kith.com/products/x"})

    assert response.status_code == 200
    assert adapter.calls == [("ca.kith.com", "x")]


@pytest.mark.parametrize(
    "url", ["https://ca.kith.com/", "https://ca.kith.com/collections/sale", "not a url", ""]
)
async def test_lookup_rejects_non_product_links(api, kith, adapter, url):
    response = await api.post("/products/lookup", json={"url": url})

    assert response.status_code == 422
    assert response.json()["detail"] == "That doesn't look like a Shopify product link"
    assert adapter.calls == []


async def test_lookup_requires_a_monitored_store(api, kith, adapter):
    # Adding a store goes through the add-store probe, never through a lookup.
    response = await api.post("/products/lookup", json={"url": "https://nrml.ca/products/x"})

    assert response.status_code == 404
    assert "Add it on the Stores page" in response.json()["detail"]
    assert adapter.calls == []


async def test_lookup_refuses_paused_and_unsupported_stores(api, session, adapter):
    session.add_all(
        [
            make_store(name="NRML", domain="nrml.ca", enabled=False),
            make_store(name="Haven", domain="havenshop.com", platform=Platform.SHOPIFY_HYDROGEN),
        ]
    )
    await session.commit()

    paused = await api.post("/products/lookup", json={"url": "https://nrml.ca/products/x"})
    headless = await api.post("/products/lookup", json={"url": "havenshop.com/products/x"})

    assert paused.status_code == 422
    assert "paused" in paused.json()["detail"]
    assert headless.status_code == 422
    assert headless.json()["detail"] == "Haven isn't supported yet"
    assert adapter.calls == []


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (ProductNotFoundError("x"), 404, "Couldn't find that product on Kith Canada"),
        (
            httpx.HTTPStatusError(
                "", request=httpx.Request("GET", "https://x"), response=httpx.Response(429)
            ),
            503,
            "Kith Canada is limiting requests right now. Try again in a few minutes.",
        ),
        (
            httpx.HTTPStatusError(
                "", request=httpx.Request("GET", "https://x"), response=httpx.Response(500)
            ),
            502,
            "Kith Canada returned an error (500)",
        ),
        (httpx.ConnectError("boom"), 502, "Couldn't reach Kith Canada"),
    ],
)
async def test_lookup_store_errors(api, kith, adapter, session, error, status, detail):
    adapter.error = error

    response = await api.post("/products/lookup", json={"url": URL})

    assert response.status_code == status
    assert response.json()["detail"] == detail
    assert await session.scalar(select(func.count()).select_from(Product)) == 0


@respx.mock
async def test_lookup_with_the_real_shopify_adapter(session, kith, admin):
    """The whole path, from a pasted URL through the real adapter, on recorded Kith data."""
    data = json.loads((FIXTURES / "kith_product.js.json").read_text(encoding="utf-8"))
    respx.get(f"https://ca.kith.com/products/{data['handle']}.js").respond(json=data)

    async def test_session():
        yield session

    async def real_adapter():
        async with httpx.AsyncClient() as client:
            yield ShopifyAdapter(client)

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_store_adapter] = real_adapter
    log_in_as(admin)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test/api") as api:
            response = await api.post(
                "/products/lookup",
                json={"url": f"https://ca.kith.com/products/{data['handle']}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == data["title"]
    assert [v["external_id"] for v in body["variants"]] == [str(v["id"]) for v in data["variants"]]
    assert body["variants"][0]["price_cents"] == 21000


# GET /products/{id}


async def test_get_product(api, kith, session):
    await api.post("/products/lookup", json={"url": URL})
    product_id = await session.scalar(select(Product.id))

    response = await api.get(f"/products/{product_id}")

    assert response.status_code == 200
    assert set(response.json()) == PRODUCT_FIELDS
    assert [v["size"] for v in response.json()["variants"]] == ["9", "10"]


async def test_get_missing_product(api):
    assert (await api.get("/products/999")).status_code == 404


# GET /products/{id}/events


async def test_events_newest_first_with_price_drop(api, kith, session):
    start = datetime(2026, 10, 1, tzinfo=UTC)
    await record_product(session, kith, product(variant("1", price=26000)), now=start)
    await record_product(
        session,
        kith,
        product(variant("1", price=21000, available=False)),
        now=start + timedelta(hours=1),
    )
    await record_product(
        session, kith, product(variant("1", price=21000)), now=start + timedelta(hours=2)
    )
    await session.commit()
    product_id = await session.scalar(select(Product.id))

    response = await api.get(f"/products/{product_id}/events")

    assert response.status_code == 200
    events = response.json()
    # The sellout and the price drop happened in the same fetch; ties are newest id first.
    assert [e["type"] for e in events] == ["restock", "price_drop", "sold_out"]
    price_drop = events[1]
    assert (price_drop["old_value"], price_drop["new_value"]) == ("26000", "21000")
    assert price_drop["variant_id"] is not None


async def test_events_limit(api, kith, session):
    start = datetime(2026, 10, 1, tzinfo=UTC)
    await record_product(session, kith, product(variant("1")), now=start)
    for hour in range(1, 6):
        await record_product(
            session,
            kith,
            product(variant("1", available=hour % 2 == 0)),
            now=start + timedelta(hours=hour),
        )
    await session.commit()
    product_id = await session.scalar(select(Product.id))

    response = await api.get(f"/products/{product_id}/events", params={"limit": 2})

    assert len(response.json()) == 2
    assert (await api.get(f"/products/{product_id}/events", params={"limit": 0})).status_code == 422


async def test_events_for_missing_product(api):
    assert (await api.get("/products/999/events")).status_code == 404


async def test_sizes_stay_in_store_order_when_one_is_added_later(api, session, adapter):
    session.add(make_store())
    await session.commit()
    adapter.product = product(variant("1", size="9"), variant("3", size="10"))
    await api.post("/products/lookup", json={"url": URL})

    # The store adds a 9.5. It gets the highest id, but belongs in the middle.
    adapter.product = product(
        variant("1", size="9"), variant("2", size="9.5"), variant("3", size="10")
    )
    response = await api.post("/products/lookup", json={"url": URL})

    assert [v["size"] for v in response.json()["variants"]] == ["9", "9.5", "10"]
    detail = await api.get(f"/products/{response.json()['id']}")
    assert [v["size"] for v in detail.json()["variants"]] == ["9", "9.5", "10"]
