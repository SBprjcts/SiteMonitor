"""The one rule for turning a pasted URL into a store's domain.

Every place that maps a URL to a store (the stores API, the CLI, product lookup) must use
this, so "https://www.NRML.ca/collections/x" and "nrml.ca" are always the same store.
The frontend mirrors it in normalizeDomain() in frontend/src/lib/format.ts.
"""

from ipaddress import ip_address
from urllib.parse import urlsplit


def normalize_domain(value: str) -> str:
    """Returns the bare lowercase hostname, without a leading "www.".

    Raises ValueError for anything that isn't a public-looking domain, including IP addresses.
    """
    trimmed = value.strip().lower()
    hostname = urlsplit(trimmed if "://" in trimmed else f"https://{trimmed}").hostname
    if not hostname or "." not in hostname:
        raise ValueError("Enter a store URL or domain, like nrml.ca")
    if _is_ip_address(hostname):
        raise ValueError("Enter the store's domain, not an IP address")
    # Only strip "www." when a domain is left behind ("www.com" itself is kept as is).
    if hostname.startswith("www.") and "." in hostname[4:]:
        hostname = hostname[4:]
    return hostname


def _is_ip_address(hostname: str) -> bool:
    try:
        ip_address(hostname)
    except ValueError:
        return False
    return True
