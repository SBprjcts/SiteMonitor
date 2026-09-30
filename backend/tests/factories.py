"""Small builders for test data, so each test only spells out what it cares about."""

from app.monitor.adapters.base import ProductData, VariantData


def variant(
    external_id: str, *, available: bool = True, price: int = 26000, size: str = ""
) -> VariantData:
    return VariantData(
        external_id=external_id,
        size=size or f"size-{external_id}",
        sku=None,
        price_cents=price,
        available=available,
    )


def product(*variants: VariantData, external_id: str = "7001") -> ProductData:
    return ProductData(
        external_id=external_id,
        handle="gel-lyte-iii",
        title="GEL-LYTE III",
        vendor="ASICS",
        image_url=None,
        url="https://ca.kith.com/products/gel-lyte-iii",
        tags=[],
        description_html="",
        variants=list(variants),
    )
