"""Throwaway prototype of the engine. Never merged into main.

Usage (from the repo root):
    python spike/watch.py https://ca.kith.com/products/<handle>

Run it once to record the current stock, then run it again later.
The second run prints every size whose stock or price changed.

Uses only the Python standard library, so there is nothing to install.
"""

import json
import sys
import urllib.request
from pathlib import Path

# Where we remember what we saw last time (ignored by git).
STATE_FILE = Path(__file__).parent / "state.json"

# Stores may block requests that don't look like a browser.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


def fetch_product(product_url: str) -> dict:
    """Step 1: FETCH. Download the product as JSON.

    Any Shopify product page URL becomes JSON by adding ".js" to the end.
    """
    url = product_url.split("?")[0].rstrip("/") + ".js"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def summarize(product: dict) -> dict:
    """Keep only what we care about: each size's stock and price.

    Each "variant" is one size. The .js endpoint gives prices in cents.
    """
    return {
        str(variant["id"]): {
            "size": variant["title"],
            "available": variant["available"],
            "price_cents": variant["price"],
        }
        for variant in product["variants"]
    }


def compare(old: dict, new: dict) -> list[str]:
    """Step 3: COMPARE. Return a line for every size that changed."""
    changes = []
    for variant_id, now in new.items():
        before = old.get(variant_id)
        if before is None:
            changes.append(f"NEW SIZE   {now['size']}")
            continue
        if not before["available"] and now["available"]:
            changes.append(f"RESTOCK    {now['size']}")
        if before["available"] and not now["available"]:
            changes.append(f"SOLD OUT   {now['size']}")
        if now["price_cents"] < before["price_cents"]:
            changes.append(
                f"PRICE DROP {now['size']}: "
                f"${before['price_cents'] / 100:.2f} -> ${now['price_cents'] / 100:.2f}"
            )
    return changes


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python spike/watch.py <shopify product url>")
    product_url = sys.argv[1]

    product = fetch_product(product_url)
    current = summarize(product)

    print(f"{product['title']}")
    for info in current.values():
        stock = "in stock" if info["available"] else "sold out"
        print(f"  {info['size']:<12} {stock:<10} ${info['price_cents'] / 100:.2f}")

    # Step 2: REMEMBER. Load last run's snapshot for this URL, if any.
    all_state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    previous = all_state.get(product_url)

    if previous is None:
        # First sighting is a baseline: nothing to compare against yet.
        print("\nFirst time seeing this product. Saved a baseline; run again later.")
    else:
        # Step 4: PRINT what changed.
        changes = compare(previous, current)
        print("\nChanges since last run:" if changes else "\nNo changes since last run.")
        for line in changes:
            print(f"  {line}")

    all_state[product_url] = current
    STATE_FILE.write_text(json.dumps(all_state, indent=2))


if __name__ == "__main__":
    main()
