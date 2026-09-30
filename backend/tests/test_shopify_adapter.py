import json
from pathlib import Path

import httpx
import pytest
import respx

from app.monitor.adapters.base import ProductNotFoundError
from app.monitor.adapters.shopify import (
    ShopifyAdapter,
    dollars_to_cents,
    parse_catalog_product,
    parse_product_js,
)

# Real responses recorded from the stores on 2026-09-29. Tests never hit live stores.
FIXTURES = Path(__file__).parent / "fixtures" / "shopify"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# Parsing /products/{handle}.js


def test_product_js_prices_are_already_cents():
    product = parse_product_js(load("kith_product.js.json"), "ca.kith.com")

    assert product.handle == "nkiq5365-600"
    assert product.url == "https://ca.kith.com/products/nkiq5365-600"
    assert product.variants[0].price_cents == 21000
    assert product.variants[0].size == "3"


def test_product_js_image_url_gets_https():
    product = parse_product_js(load("kith_product.js.json"), "ca.kith.com")

    assert product.image_url.startswith("https://cdn.shopify.com/")


def test_size_is_found_when_it_is_not_the_first_option():
    # JD Sports lists Color first, so the variant title is "Black / 5".
    product = parse_product_js(load("jdsports_product.js.json"), "jdsports.ca")

    assert product.variants[0].size == "5"
    assert all("/" not in v.size for v in product.variants)


# Parsing /products.json


def test_catalog_prices_are_converted_to_cents():
    products = [
        parse_catalog_product(p, "ca.kith.com") for p in load("kith_catalog.json")["products"]
    ]

    assert len(products) == 3
    assert products[0].variants[0].price_cents == 21000


def test_catalog_size_option_is_matched_case_insensitively():
    # NRML's options are [SIZE, COLOR, STYLE]; variant title is "M / BLUE / 1140372-BLUE".
    product = parse_catalog_product(load("nrml_catalog.json")["products"][0], "nrml.ca")

    assert product.variants[0].size == "M"


def test_both_endpoints_agree_on_the_same_product():
    # The Kith fixtures are the same shoe, recorded seconds apart.
    from_js = parse_product_js(load("kith_product.js.json"), "ca.kith.com")
    from_catalog = parse_catalog_product(load("kith_catalog.json")["products"][0], "ca.kith.com")

    def sizes_and_prices(product):
        return [(v.external_id, v.size, v.price_cents) for v in product.variants]

    assert from_js.external_id == from_catalog.external_id
    assert sizes_and_prices(from_js) == sizes_and_prices(from_catalog)
    assert from_js.image_url.split("?")[0] == from_catalog.image_url.split("?")[0]


# Edge cases


@pytest.mark.parametrize(
    ("price", "cents"),
    [("210.00", 21000), ("19.99", 1999), ("0.10", 10), ("85", 8500), ("129.5", 12950)],
)
def test_dollars_to_cents(price, cents):
    assert dollars_to_cents(price) == cents


def test_product_without_options_is_one_size():
    data = {
        "id": 1,
        "handle": "tote",
        "title": "Tote",
        "tags": "bags, accessories",
        "options": [{"name": "Title", "position": 1, "values": ["Default Title"]}],
        "variants": [
            {
                "id": 2,
                "title": "Default Title",
                "option1": "Default Title",
                "sku": "",
                "price": "40.00",
                "available": True,
            }
        ],
    }

    product = parse_catalog_product(data, "example.com")

    assert product.variants[0].size == "One Size"
    assert product.variants[0].sku is None
    assert product.tags == ["bags", "accessories"]
    assert product.image_url is None


# Fetching (HTTP is mocked with respx)


@pytest.fixture
async def adapter():
    async with httpx.AsyncClient() as client:
        yield ShopifyAdapter(client)


@respx.mock
async def test_fetch_product(adapter):
    respx.get("https://ca.kith.com/products/nkiq5365-600.js").respond(
        json=load("kith_product.js.json")
    )

    product = await adapter.fetch_product("ca.kith.com", "nkiq5365-600")

    assert product.title == load("kith_product.js.json")["title"]


@respx.mock
async def test_fetch_missing_product_raises_not_found(adapter):
    respx.get("https://ca.kith.com/products/gone.js").respond(404)

    with pytest.raises(ProductNotFoundError):
        await adapter.fetch_product("ca.kith.com", "gone")


@respx.mock
async def test_fetch_server_error_raises(adapter):
    # Solestop returns intermittent 503s; phase 2's rate limiter backs off on these.
    respx.get("https://solestop.com/products/x.js").respond(503)

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.fetch_product("solestop.com", "x")


@respx.mock
async def test_fetch_catalog_page_sends_limit_and_page(adapter):
    route = respx.get("https://nrml.ca/products.json", params={"limit": 250, "page": 2}).respond(
        json=load("nrml_catalog.json")
    )

    products = await adapter.fetch_catalog_page("nrml.ca", 2)

    assert route.called
    assert len(products) == 3


@respx.mock
async def test_fetch_catalog_past_last_page_is_empty(adapter):
    respx.get("https://nrml.ca/products.json").respond(json={"products": []})

    assert await adapter.fetch_catalog_page("nrml.ca", 99) == []
