"""Text normalization for style-code and keyword watches (slice C).

Only search_text is built here so far; the watch matcher comes with slice C.
"""

import html
import re

from app.monitor.adapters.base import ProductData

_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def build_search_text(product: ProductData) -> str:
    """Everything a style code or keyword could appear in, as one lowercase string.

    Built from the title, handle, tags, description (HTML stripped), and variant SKUs,
    since the style code can be in any of them (the SKU often isn't it; see CLAUDE.md).
    Words stay separated so keyword watches can match whole words; the style-code matcher
    removes "-" and spaces from both sides when it compares.
    """
    skus = dict.fromkeys(v.sku for v in product.variants if v.sku)  # dedupe, keep order
    parts = [
        product.title,
        product.handle,
        *product.tags,
        _strip_html(product.description_html),
        *skus,
    ]
    return _WHITESPACE.sub(" ", " ".join(parts)).strip().lower()


def _strip_html(text: str) -> str:
    # Tags become spaces so "<p>DD1391</p><p>100</p>" doesn't merge into one word.
    return html.unescape(_TAG.sub(" ", text))
