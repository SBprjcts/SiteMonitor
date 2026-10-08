import httpx

from app.monitor.ratelimit import RateLimitedTransport

# Stores may block requests that don't look like a browser (see CLAUDE.md).
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


def create_http_client() -> httpx.AsyncClient:
    """The HTTP client for all requests to stores.

    Every request goes through the shared per-store rate limiter (monitor/ratelimit.py),
    whichever client sends it. A store that is backing off raises StoreBusyError instead
    of making the caller wait.
    """
    return httpx.AsyncClient(
        transport=RateLimitedTransport(httpx.AsyncHTTPTransport()),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=15,
        follow_redirects=True,
    )
