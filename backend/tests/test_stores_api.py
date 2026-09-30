import httpx
import pytest
import respx

from app.db.models import Platform, Store
from app.db.session import get_session
from app.main import app
from app.stores import probe as probe_module
from app.stores.domain import normalize_domain
from app.stores.probe import get_store_probe, is_public_host, probe_shopify_store


class FakeProbe:
    """Stands in for the real Shopify probe so tests never hit a live store."""

    def __init__(self) -> None:
        self.ok = True
        self.calls: list[str] = []

    async def __call__(self, domain: str) -> bool:
        self.calls.append(domain)
        return self.ok


@pytest.fixture
def probe():
    return FakeProbe()


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """Every hostname resolves to one public address, so tests never do real DNS lookups."""
    addresses = ["93.184.216.34"]

    async def resolve(host):
        return addresses

    monkeypatch.setattr(probe_module, "resolve_host", resolve)
    return addresses


@pytest.fixture
async def api(session, probe):
    """An API client wired to the test database and the fake probe."""

    async def test_session():
        yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_store_probe] = lambda: probe
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def stores(session):
    rows = [
        Store(name="Kith Canada", domain="ca.kith.com", hot_interval_s=15, sweep_interval_s=60),
        Store(
            name="Haven",
            domain="havenshop.com",
            platform=Platform.SHOPIFY_HYDROGEN,
            enabled=False,
            hot_interval_s=15,
            sweep_interval_s=60,
        ),
    ]
    session.add_all(rows)
    await session.commit()
    return rows


# The fields the frontend's Store type expects (frontend/src/api/types.ts).
STORE_FIELDS = {
    "id",
    "name",
    "domain",
    "platform",
    "enabled",
    "status",
    "hot_interval_s",
    "sweep_interval_s",
    "last_ok_at",
    "consecutive_errors",
}


async def test_list_stores(api, stores):
    response = await api.get("/stores")

    assert response.status_code == 200
    body = response.json()
    assert [s["domain"] for s in body] == ["ca.kith.com", "havenshop.com"]
    assert set(body[0]) == STORE_FIELDS
    assert body[1]["platform"] == "shopify_hydrogen"


async def test_disable_and_reenable_store(api, stores):
    store_id = stores[0].id

    response = await api.patch(f"/stores/{store_id}", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["enabled"] is False

    listed = (await api.get("/stores")).json()
    assert listed[0]["enabled"] is False

    response = await api.patch(f"/stores/{store_id}", json={"enabled": True})
    assert response.json()["enabled"] is True


async def test_update_missing_store(api, stores):
    response = await api.patch("/stores/999", json={"enabled": True})

    assert response.status_code == 404


async def test_cannot_enable_hydrogen_store(api, stores):
    response = await api.patch(f"/stores/{stores[1].id}", json={"enabled": True})

    assert response.status_code == 422
    assert response.json()["detail"] == "Haven isn't supported yet"


async def test_add_store_normalizes_domain(api, stores, probe):
    response = await api.post(
        "/stores", json={"domain": " https://www.NewShop.ca/collections/sale "}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["domain"] == "newshop.ca"
    assert body["name"] == "newshop.ca"
    assert body["platform"] == "shopify"
    assert body["enabled"] is True
    assert body["hot_interval_s"] == 15
    assert probe.calls == ["newshop.ca"]
    assert len((await api.get("/stores")).json()) == 3


async def test_add_store_with_name(api, stores):
    response = await api.post("/stores", json={"domain": "nrml.ca", "name": "  NRML  "})

    assert response.json()["name"] == "NRML"


async def test_add_duplicate_store(api, stores, probe):
    response = await api.post("/stores", json={"domain": "HTTPS://ca.kith.com/"})

    assert response.status_code == 409
    assert response.json()["detail"] == "ca.kith.com is already being monitored"
    assert probe.calls == []


async def test_www_and_bare_domain_are_the_same_store(api, stores, probe):
    # Otherwise the same store would be monitored twice: double requests and double alerts.
    assert (await api.post("/stores", json={"domain": "nrml.ca"})).status_code == 201

    response = await api.post("/stores", json={"domain": "https://www.nrml.ca/"})

    assert response.status_code == 409
    assert response.json()["detail"] == "nrml.ca is already being monitored"


async def test_add_store_that_is_not_shopify(api, stores, probe):
    probe.ok = False

    response = await api.post("/stores", json={"domain": "example.com"})

    assert response.status_code == 422
    assert "example.com" in response.json()["detail"]
    assert len((await api.get("/stores")).json()) == 2


@pytest.mark.parametrize(
    "domain",
    [
        "",
        "   ",
        "localhost",
        "not a domain",
        "127.0.0.1",
        "http://169.254.169.254/latest/meta-data",
        "10.0.0.5",
        "[::1]",
    ],
)
async def test_add_store_rejects_invalid_domain(api, stores, probe, domain):
    response = await api.post("/stores", json={"domain": domain})

    assert response.status_code == 422
    assert probe.calls == []


@pytest.mark.parametrize(
    ("value", "domain"),
    [
        ("nrml.ca", "nrml.ca"),
        ("https://www.NRML.ca/collections/new?page=2", "nrml.ca"),
        ("WWW.kith.com", "kith.com"),
        ("ca.kith.com", "ca.kith.com"),
        ("www.com", "www.com"),
        ("  https://shop.www-store.ca/  ", "shop.www-store.ca"),
    ],
)
def test_normalize_domain(value, domain):
    assert normalize_domain(value) == domain


@pytest.mark.parametrize("value", ["127.0.0.1", "https://[2001:db8::1]/"])
def test_normalize_domain_rejects(value):
    with pytest.raises(ValueError):
        normalize_domain(value)


# The real probe, against mocked HTTP.

FEED = "https://shop.example.ca/products.json"


@respx.mock
async def test_probe_accepts_shopify_feed():
    respx.get(FEED, params={"limit": "1"}).respond(json={"products": [{"id": 1}]})

    assert await probe_shopify_store("shop.example.ca") is True


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        # Headless (Hydrogen) Shopify stores serve an empty list.
        httpx.Response(200, json={"products": []}),
        httpx.Response(200, json={"items": []}),
        httpx.Response(200, text="<html></html>"),
        httpx.Response(404),
        httpx.Response(503),
    ],
)
async def test_probe_rejects_non_shopify_responses(response):
    respx.get(FEED, params={"limit": "1"}).mock(return_value=response)

    assert await probe_shopify_store("shop.example.ca") is False


@respx.mock
async def test_probe_handles_connection_errors():
    respx.get(FEED, params={"limit": "1"}).mock(side_effect=httpx.ConnectError("boom"))

    assert await probe_shopify_store("shop.example.ca") is False


@respx.mock
async def test_probe_refuses_domains_that_resolve_to_private_addresses(fake_dns):
    fake_dns[:] = ["10.0.0.5"]
    route = respx.get(FEED, params={"limit": "1"}).respond(json={"products": [{"id": 1}]})

    assert await probe_shopify_store("shop.example.ca") is False
    assert not route.called


@respx.mock
async def test_probe_refuses_redirects_to_private_addresses():
    respx.get(FEED, params={"limit": "1"}).respond(
        302, headers={"Location": "http://169.254.169.254/latest/meta-data"}
    )
    metadata = respx.get("http://169.254.169.254/latest/meta-data").respond(200)

    assert await probe_shopify_store("shop.example.ca") is False
    assert not metadata.called


@pytest.mark.parametrize(
    ("resolved", "public"),
    [
        (["93.184.216.34"], True),
        (["127.0.0.1"], False),
        (["93.184.216.34", "192.168.1.10"], False),  # one private address is enough
        (["fe80::1%12"], False),
        ([], False),
    ],
)
async def test_is_public_host(fake_dns, resolved, public):
    fake_dns[:] = resolved

    assert await is_public_host("shop.example.ca") is public


async def test_is_public_host_when_dns_fails(monkeypatch):
    async def fail(host):
        raise OSError("no such host")

    monkeypatch.setattr(probe_module, "resolve_host", fail)

    assert await is_public_host("nope.example.ca") is False
