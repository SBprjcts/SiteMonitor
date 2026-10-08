import httpx

from app.monitor.ratelimit import RateLimitedTransport

# We say who we are. Claiming to be Chrome got the .js endpoint refused far more often:
# Cloudflare can tell when a client isn't the browser it names (see CLAUDE.md).
USER_AGENT = "SiteMonitor/0.1 (+https://github.com/SBprjcts/SiteMonitor)"


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
