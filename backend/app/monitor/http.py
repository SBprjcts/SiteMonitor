import httpx

# Stores may block requests that don't look like a browser (see CLAUDE.md).
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


def create_http_client() -> httpx.AsyncClient:
    """The HTTP client for all requests to stores.

    Phase 2 adds the per-domain rate limiter here, so adapters get it for free.
    """
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=15,
        follow_redirects=True,
    )
