import pytest
from sqlalchemy import select

from app.db.models import Store
from app.monitor.__main__ import main, run_once
from app.monitor.adapters.base import ProductData
from app.monitor.adapters.shopify import parse_product_url
from tests.factories import product, variant

URL = "https://ca.kith.com/products/gel-lyte-iii"


class FakeAdapter:
    """Returns whatever product state the test sets, instead of calling a store."""

    def __init__(self) -> None:
        self.state: ProductData | None = None
        self.requested: list[tuple[str, str]] = []

    async def fetch_product(self, domain: str, handle: str) -> ProductData:
        self.requested.append((domain, handle))
        return self.state

    async def fetch_catalog_page(self, domain: str, page: int) -> list[ProductData]:
        return []


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://ca.kith.com/products/gel-lyte-iii", ("ca.kith.com", "gel-lyte-iii")),
        ("https://www.nrml.ca/collections/new/products/rugby?variant=1", ("nrml.ca", "rugby")),
        ("ca.kith.com/products/gel-lyte-iii.js", ("ca.kith.com", "gel-lyte-iii")),
        ("https://CA.KITH.COM/products/gel-lyte-iii/", ("ca.kith.com", "gel-lyte-iii")),
        ("https://www.nrml.ca:443/products/rugby", ("nrml.ca", "rugby")),
    ],
)
def test_parse_product_url(url, expected):
    assert parse_product_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://ca.kith.com/",
        "https://ca.kith.com/products",
        "nonsense",
        "http://127.0.0.1/products/x",
    ],
)
def test_parse_product_url_rejects_non_product_urls(url):
    with pytest.raises(ValueError):
        parse_product_url(url)


async def test_first_run_is_a_baseline_then_changes_are_reported(session):
    adapter = FakeAdapter()
    session.add(
        Store(name="Kith Canada", domain="ca.kith.com", hot_interval_s=15, sweep_interval_s=60)
    )

    adapter.state = product(
        variant("1", size="9", available=False), variant("2", size="10", price=26000)
    )
    first = await run_once(session, adapter, URL)

    adapter.state = product(
        variant("1", size="9", available=True), variant("2", size="10", price=19500)
    )
    second = await run_once(session, adapter, URL)

    third = await run_once(session, adapter, URL)

    assert adapter.requested[0] == ("ca.kith.com", "gel-lyte-iii")
    assert first[0] == "GEL-LYTE III  [Kith Canada]"
    assert first[-1].startswith("First time seeing this product")
    assert second[-3:] == [
        "Changes since the last run:",
        "  RESTOCK     9",
        "  PRICE_DROP  10  $260.00 -> $195.00",
    ]
    assert third[-1] == "No changes since the last run."


async def test_unknown_store_is_added(session):
    adapter = FakeAdapter()
    adapter.state = product(variant("1"))

    lines = await run_once(session, adapter, "https://someshop.com/products/gel-lyte-iii")

    assert lines[0] == "(added someshop.com as a new store)"
    assert await session.scalar(select(Store.domain)) == "someshop.com"


async def test_main_without_once_explains_what_to_do(capsys):
    with pytest.raises(SystemExit):
        await main([])

    assert "--once" in capsys.readouterr().err
