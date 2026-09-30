import json
from pathlib import Path

from app.monitor.adapters.shopify import parse_product_js
from app.monitor.matching import build_search_text
from tests.factories import product, variant

FIXTURES = Path(__file__).parent / "fixtures" / "shopify"


def test_search_text_covers_every_field_lowercased():
    data = product(variant("1"), variant("2")).model_copy(
        update={
            "title": "Air Jordan 4 'Military Blue'",
            "handle": "aj4-military-blue",
            "tags": ["Jordan", "Mens"],
            "description_html": "<p>Style: FV5029-141</p>",
        }
    )
    data.variants[0].sku = "FV5029-141-9"

    text = build_search_text(data)

    assert text == (
        "air jordan 4 'military blue' aj4-military-blue jordan mens style: fv5029-141 fv5029-141-9"
    )


def test_html_is_stripped_without_merging_words():
    data = product(variant("1")).model_copy(
        update={"title": "", "handle": "", "description_html": "<p>DD1391</p><p>100 &amp; up</p>"}
    )

    assert build_search_text(data) == "dd1391 100 & up"


def test_repeated_skus_are_listed_once():
    data = product(variant("1"), variant("2")).model_copy(update={"title": "", "handle": ""})
    for v in data.variants:
        v.sku = "KF0954"

    assert build_search_text(data) == "kf0954"


def test_real_kith_product_includes_the_style_code_from_the_handle():
    # Kith's style code (IQ5365-600) isn't in the title or SKUs, only in the handle.
    data = json.loads((FIXTURES / "kith_product.js.json").read_text(encoding="utf-8"))

    text = build_search_text(parse_product_js(data, "ca.kith.com"))

    assert "nkiq5365-600" in text
    assert "nike air bakin high sp" in text
    assert "rope laces" in text  # from the description
    assert "<p>" not in text
