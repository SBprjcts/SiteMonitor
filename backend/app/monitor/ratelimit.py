"""Per-store rate limiting, backoff, and a circuit breaker. See CLAUDE.md.

Every request to a store goes through `RateLimitedTransport` (wired up in
`monitor/http.py`), which asks the shared `limiter` before sending:

- Spacing, per store: one request every `DOMAIN_MIN_REQUEST_GAP_S`, plus jitter, and never
  two at the same time. This is a token bucket holding a single token.
- Backoff, per store and endpoint: a 429, 403, 5xx, or connection error doubles the wait
  before the next request to that endpoint, honoring `Retry-After`. A good response resets it.
- Circuit breaker, per store and endpoint: after `DEGRADED_AFTER` failures in a row it is
  `degraded` and polled slowly until one request succeeds.

Backoff is tracked per endpoint because Shopify throttles them separately: the product
`.js` endpoint gets 429s while the catalog keeps answering. A refused product page must not
stall the catalog sweep, which is the dependable source, or mark the whole store degraded.

The state lives in this process, not in an HTTP client, so short-lived clients (the product
lookup makes one per request) still share one budget per store. It is not shared between
processes: on the VPS, the API and the monitor containers each keep their own.
"""

import asyncio
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum

import httpx

from app.config import get_settings

JITTER = 0.25  # up to 25% extra on every wait, so requests don't land on a fixed beat
BACKOFF_BASE_S = 5.0  # wait after the first failure; doubles with each one after
BACKOFF_MAX_S = 300.0
RETRY_AFTER_MAX_S = 900.0  # don't let a store park us for hours with a huge Retry-After
DEGRADED_AFTER = 5  # consecutive failures before an endpoint counts as degraded
DEGRADED_GAP_S = 60.0  # spacing while degraded
# Waiting longer than this isn't worth it for a caller: they get StoreBusyError instead.
MAX_WAIT_S = 10.0


class Endpoint(StrEnum):
    """The groups of store URLs that back off independently."""

    CATALOG = "catalog"  # /products.json, and anything that isn't a product page
    PRODUCT = "product"  # /products/{handle}.js


def endpoint_for(path: str) -> Endpoint:
    if path.endswith(".js") and "/products/" in path:
        return Endpoint.PRODUCT
    return Endpoint.CATALOG


class StoreBusyError(httpx.TransportError):
    """The store is backing off, so the request was not sent. Try again later."""

    def __init__(self, domain: str, retry_in_s: float) -> None:
        super().__init__(f"{domain} is backing off; next request allowed in {retry_in_s:.0f}s")
        self.domain = domain
        self.retry_in_s = retry_in_s


@dataclass(frozen=True)
class EndpointHealth:
    """A snapshot of one endpoint. The scheduler copies the catalog's onto the `stores` row."""

    consecutive_errors: int
    degraded: bool
    last_status: int | None  # the last HTTP status, or None after a connection error
    retry_in_s: float  # how long until the next request is allowed (0 if now)


@dataclass
class _EndpointState:
    blocked_until: float = 0.0
    consecutive_errors: int = 0
    last_status: int | None = None


@dataclass
class _DomainState:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    next_slot_at: float = 0.0  # spacing, shared by every endpoint of the store
    endpoints: dict[Endpoint, _EndpointState] = field(default_factory=dict)

    def endpoint(self, endpoint: Endpoint) -> _EndpointState:
        return self.endpoints.setdefault(endpoint, _EndpointState())


def domain_key(host: str) -> str:
    """ "WWW.Foosh.ca" and "foosh.ca" are one store, so they share one budget."""
    return host.lower().removeprefix("www.")


class RateLimiter:
    def __init__(
        self,
        *,
        min_gap_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._min_gap_s = min_gap_s
        self._clock = clock
        self._sleep = sleep
        self._jitter = jitter
        self._domains: dict[str, _DomainState] = {}

    @property
    def min_gap_s(self) -> float:
        if self._min_gap_s is not None:
            return self._min_gap_s
        return get_settings().domain_min_request_gap_s

    def reset(self) -> None:
        """Forgets every store. For tests."""
        self._domains.clear()

    def health(self, host: str, endpoint: Endpoint = Endpoint.CATALOG) -> EndpointHealth:
        state = self._domains.get(domain_key(host)) or _DomainState()
        ep = state.endpoints.get(endpoint) or _EndpointState()
        return EndpointHealth(
            consecutive_errors=ep.consecutive_errors,
            degraded=ep.consecutive_errors >= DEGRADED_AFTER,
            last_status=ep.last_status,
            retry_in_s=max(0.0, max(state.next_slot_at, ep.blocked_until) - self._clock()),
        )

    @asynccontextmanager
    async def slot(
        self,
        host: str,
        endpoint: Endpoint = Endpoint.CATALOG,
        max_wait_s: float = MAX_WAIT_S,
    ) -> AsyncIterator["_Slot"]:
        """Waits for this store's turn, then holds it for one request.

            async with limiter.slot("ca.kith.com", Endpoint.PRODUCT) as slot:
                response = await send()
                slot.record(response.status_code, response.headers.get("Retry-After"))

        Leaving the block without calling `record` (the request raised) counts as a failure.
        Raises StoreBusyError instead of waiting longer than `max_wait_s`.
        """
        key = domain_key(host)
        state = self._domains.setdefault(key, _DomainState())
        ep = state.endpoint(endpoint)

        try:
            await asyncio.wait_for(state.lock.acquire(), timeout=max_wait_s)
        except TimeoutError:
            raise StoreBusyError(key, max_wait_s) from None
        try:
            wait = max(state.next_slot_at, ep.blocked_until) - self._clock()
            if wait > max_wait_s:
                raise StoreBusyError(key, wait)
            if wait > 0:
                await self._sleep(wait)

            slot = _Slot()
            try:
                yield slot
            except asyncio.CancelledError:
                # We gave up (the caller went away); that says nothing about the store.
                slot.cancelled = True
                raise
            finally:
                self._finish(state, ep, slot)
        finally:
            state.lock.release()

    def _finish(self, state: _DomainState, ep: _EndpointState, slot: "_Slot") -> None:
        now = self._clock()
        # Spacing applies after every request, whatever happened to it.
        state.next_slot_at = now + self._with_jitter(self.min_gap_s)
        if slot.cancelled:
            return

        ep.last_status = slot.status
        if slot.ok:
            ep.consecutive_errors = 0
            ep.blocked_until = 0.0
            return

        ep.consecutive_errors += 1
        backoff = min(BACKOFF_BASE_S * 2 ** (ep.consecutive_errors - 1), BACKOFF_MAX_S)
        delay = max(backoff, slot.retry_after_s)
        if ep.consecutive_errors >= DEGRADED_AFTER:
            delay = max(delay, DEGRADED_GAP_S)
        ep.blocked_until = now + self._with_jitter(delay)

    def _with_jitter(self, seconds: float) -> float:
        return seconds * (1 + JITTER * self._jitter())


class _Slot:
    """One request's outcome, reported back to the limiter."""

    def __init__(self) -> None:
        self.status: int | None = None
        self.ok = False
        self.retry_after_s = 0.0
        self.cancelled = False

    def record(self, status: int, retry_after: str | None = None) -> None:
        self.status = status
        # A 404 is a fine answer (the product is gone). 403 is how stores block clients.
        self.ok = status not in (403, 429) and status < 500
        self.retry_after_s = 0.0 if self.ok else parse_retry_after(retry_after)


def parse_retry_after(value: str | None) -> float:
    """Seconds to wait from a Retry-After header ("120" or an HTTP date). 0 if unusable."""
    if not value:
        return 0.0
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return 0.0
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        seconds = (when - datetime.now(UTC)).total_seconds()
    return min(max(seconds, 0.0), RETRY_AFTER_MAX_S)


# The one limiter for this process. Tests reset it between cases.
limiter = RateLimiter()


class RateLimitedTransport(httpx.AsyncBaseTransport):
    """Sends each request through the limiter. Redirect hops pass through here too,
    so `foosh.ca` -> `www.foosh.ca` counts as two requests to the same store."""

    def __init__(self, inner: httpx.AsyncBaseTransport, limiter: RateLimiter = limiter) -> None:
        self._inner = inner
        self._limiter = limiter

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        endpoint = endpoint_for(request.url.path)
        async with self._limiter.slot(request.url.host, endpoint) as slot:
            response = await self._inner.handle_async_request(request)
            slot.record(response.status_code, response.headers.get("Retry-After"))
            return response

    async def aclose(self) -> None:
        await self._inner.aclose()
