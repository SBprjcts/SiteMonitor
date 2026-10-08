import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
import respx

from app.monitor.http import USER_AGENT, create_http_client
from app.monitor.ratelimit import (
    BACKOFF_BASE_S,
    BACKOFF_MAX_S,
    DEGRADED_AFTER,
    DEGRADED_GAP_S,
    JITTER,
    MAX_WAIT_S,
    RETRY_AFTER_MAX_S,
    Endpoint,
    RateLimiter,
    StoreBusyError,
    endpoint_for,
    limiter,
    parse_retry_after,
)

GAP = 2.0


class FakeTime:
    """A clock that only moves when the limiter sleeps, so tests are exact and instant."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_time():
    return FakeTime()


@pytest.fixture
def limits(fake_time):
    """A limiter on the fake clock, with jitter switched off."""
    return RateLimiter(
        min_gap_s=GAP, clock=fake_time.clock, sleep=fake_time.sleep, jitter=lambda: 0.0
    )


async def request(
    limits,
    host="ca.kith.com",
    status=200,
    retry_after=None,
    max_wait_s=None,
    endpoint=Endpoint.CATALOG,
):
    kwargs = {} if max_wait_s is None else {"max_wait_s": max_wait_s}
    async with limits.slot(host, endpoint, **kwargs) as slot:
        slot.record(status, retry_after)


# Spacing


async def test_first_request_goes_straight_out(limits, fake_time):
    await request(limits)

    assert fake_time.sleeps == []


async def test_second_request_to_the_same_store_waits_for_the_gap(limits, fake_time):
    await request(limits)
    await request(limits)

    assert fake_time.sleeps == [GAP]


async def test_time_already_passed_counts_towards_the_gap(limits, fake_time):
    await request(limits)
    fake_time.now += 1.5
    await request(limits)

    assert fake_time.sleeps == [pytest.approx(0.5)]


async def test_different_stores_do_not_wait_for_each_other(limits, fake_time):
    await request(limits, "ca.kith.com")
    await request(limits, "nrml.ca")

    assert fake_time.sleeps == []


async def test_www_and_bare_domain_share_one_budget(limits, fake_time):
    await request(limits, "foosh.ca")
    await request(limits, "WWW.Foosh.ca")

    assert fake_time.sleeps == [GAP]


async def test_jitter_adds_up_to_a_quarter_of_the_wait(fake_time):
    limits = RateLimiter(
        min_gap_s=GAP, clock=fake_time.clock, sleep=fake_time.sleep, jitter=lambda: 1.0
    )
    await request(limits)
    await request(limits)

    assert fake_time.sleeps == [pytest.approx(GAP * (1 + JITTER))]


async def test_requests_to_one_store_never_overlap(limits):
    in_flight = 0
    most_at_once = 0

    async def slow_request():
        nonlocal in_flight, most_at_once
        async with limits.slot("ca.kith.com") as slot:
            in_flight += 1
            most_at_once = max(most_at_once, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            slot.record(200)

    await asyncio.gather(*(slow_request() for _ in range(4)))

    assert most_at_once == 1


# Backoff


@pytest.mark.parametrize("status", [429, 403, 500, 503])
async def test_a_failure_backs_off_longer_than_the_gap(limits, fake_time, status):
    await request(limits, status=status)
    await request(limits)

    assert fake_time.sleeps == [BACKOFF_BASE_S]


async def test_a_404_is_a_normal_answer_not_a_failure(limits, fake_time):
    await request(limits, status=404)
    await request(limits)

    assert fake_time.sleeps == [GAP]
    assert limits.health("ca.kith.com").consecutive_errors == 0


async def test_backoff_doubles_with_each_failure_in_a_row(limits):
    waits = []
    for _ in range(4):
        await request(limits, status=503, max_wait_s=10_000)
        waits.append(limits.health("ca.kith.com").retry_in_s)

    assert waits == [5.0, 10.0, 20.0, 40.0]


async def test_backoff_stops_growing_at_the_maximum(limits):
    for _ in range(12):
        await request(limits, status=503, max_wait_s=10_000)

    assert limits.health("ca.kith.com").retry_in_s == BACKOFF_MAX_S


async def test_a_good_response_resets_the_backoff(limits, fake_time):
    for _ in range(3):
        await request(limits, status=503, max_wait_s=10_000)

    await request(limits, status=200, max_wait_s=10_000)

    health = limits.health("ca.kith.com")
    assert health.consecutive_errors == 0
    assert health.retry_in_s == GAP


async def test_retry_after_is_honored_when_it_is_longer_than_the_backoff(limits):
    await request(limits, status=429, retry_after="120")

    assert limits.health("ca.kith.com").retry_in_s == 120


async def test_a_short_retry_after_does_not_shorten_the_backoff(limits):
    await request(limits, status=429, retry_after="1")

    assert limits.health("ca.kith.com").retry_in_s == BACKOFF_BASE_S


async def test_a_request_that_raises_counts_as_a_failure(limits):
    with pytest.raises(httpx.ConnectError):
        async with limits.slot("ca.kith.com"):
            raise httpx.ConnectError("boom")

    health = limits.health("ca.kith.com")
    assert health.consecutive_errors == 1
    assert health.last_status is None
    assert health.retry_in_s == BACKOFF_BASE_S


async def test_a_cancelled_request_is_not_held_against_the_store(limits):
    with pytest.raises(asyncio.CancelledError):
        async with limits.slot("ca.kith.com"):
            raise asyncio.CancelledError

    health = limits.health("ca.kith.com")
    assert health.consecutive_errors == 0
    assert health.retry_in_s == GAP


# Endpoints back off separately


@pytest.mark.parametrize(
    ("path", "endpoint"),
    [
        ("/products/gel-lyte-iii.js", Endpoint.PRODUCT),
        ("/collections/new/products/gel-lyte-iii.js", Endpoint.PRODUCT),
        ("/products.json", Endpoint.CATALOG),
        ("/products/gel-lyte-iii.json", Endpoint.CATALOG),
        ("/assets/theme.js", Endpoint.CATALOG),
        ("/", Endpoint.CATALOG),
    ],
)
def test_endpoint_for(path, endpoint):
    assert endpoint_for(path) is endpoint


async def test_a_refused_product_page_does_not_stall_the_catalog(limits, fake_time):
    await request(limits, status=429, retry_after="60", endpoint=Endpoint.PRODUCT)

    await request(limits, endpoint=Endpoint.CATALOG)  # goes out after the normal gap

    assert fake_time.sleeps == [GAP]
    assert limits.health("ca.kith.com", Endpoint.CATALOG).consecutive_errors == 0
    with pytest.raises(StoreBusyError):
        await request(limits, endpoint=Endpoint.PRODUCT)


async def test_spacing_is_still_shared_between_endpoints(limits, fake_time):
    await request(limits, endpoint=Endpoint.PRODUCT)
    await request(limits, endpoint=Endpoint.CATALOG)
    await request(limits, endpoint=Endpoint.PRODUCT)

    assert fake_time.sleeps == [GAP, GAP]


async def test_refused_product_pages_do_not_mark_the_catalog_degraded(limits):
    for _ in range(DEGRADED_AFTER):
        await request(limits, status=429, endpoint=Endpoint.PRODUCT, max_wait_s=10_000)

    assert limits.health("ca.kith.com", Endpoint.PRODUCT).degraded is True
    assert limits.health("ca.kith.com", Endpoint.CATALOG).degraded is False


async def test_a_good_catalog_response_does_not_clear_the_product_backoff(limits):
    await request(limits, status=429, retry_after="60", endpoint=Endpoint.PRODUCT)
    await request(limits, status=200, endpoint=Endpoint.CATALOG)

    product = limits.health("ca.kith.com", Endpoint.PRODUCT)
    assert product.consecutive_errors == 1
    assert product.retry_in_s > MAX_WAIT_S


# Failing fast


async def test_a_long_backoff_raises_instead_of_making_the_caller_wait(limits, fake_time):
    await request(limits, status=429, retry_after="120")

    with pytest.raises(StoreBusyError) as error:
        await request(limits)

    assert error.value.domain == "ca.kith.com"
    assert error.value.retry_in_s == 120
    assert fake_time.sleeps == []  # it didn't wait, and nothing was sent
    assert limits.health("ca.kith.com").consecutive_errors == 1  # and it isn't a new failure


async def test_the_request_goes_through_once_the_backoff_has_passed(limits, fake_time):
    await request(limits, status=429, retry_after="120")
    fake_time.now += 120

    await request(limits)

    assert limits.health("ca.kith.com").consecutive_errors == 0


async def test_a_wait_within_the_limit_is_just_waited(limits, fake_time):
    await request(limits, status=503)  # 5s backoff, under MAX_WAIT_S
    await request(limits)

    assert BACKOFF_BASE_S < MAX_WAIT_S
    assert fake_time.sleeps == [BACKOFF_BASE_S]


# Circuit breaker


async def test_store_is_degraded_after_enough_failures_in_a_row(limits):
    for _ in range(DEGRADED_AFTER - 1):
        await request(limits, status=503, max_wait_s=10_000)
    assert limits.health("ca.kith.com").degraded is False

    await request(limits, status=503, max_wait_s=10_000)

    health = limits.health("ca.kith.com")
    assert health.degraded is True
    assert health.last_status == 503
    assert health.retry_in_s >= DEGRADED_GAP_S


async def test_a_degraded_store_recovers_on_the_first_good_response(limits):
    for _ in range(DEGRADED_AFTER):
        await request(limits, status=503, max_wait_s=10_000)

    await request(limits, status=200, max_wait_s=10_000)

    health = limits.health("ca.kith.com")
    assert health.degraded is False
    assert health.retry_in_s == GAP


def test_a_store_never_requested_is_healthy(limits):
    health = limits.health("nrml.ca")

    assert (health.consecutive_errors, health.degraded, health.retry_in_s) == (0, False, 0.0)


# Retry-After parsing


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        (None, 0.0),
        ("", 0.0),
        ("120", 120.0),
        ("0", 0.0),
        ("-5", 0.0),
        ("soon", 0.0),
        ("999999", RETRY_AFTER_MAX_S),
    ],
)
def test_parse_retry_after(value, seconds):
    assert parse_retry_after(value) == seconds


def test_parse_retry_after_http_date():
    in_a_minute = format_datetime(datetime.now(UTC) + timedelta(seconds=60), usegmt=True)
    last_year = format_datetime(datetime.now(UTC) - timedelta(days=365), usegmt=True)

    assert parse_retry_after(in_a_minute) == pytest.approx(60, abs=2)
    assert parse_retry_after(last_year) == 0.0


# Through the real HTTP client (requests mocked with respx)


@respx.mock
async def test_every_client_shares_the_one_limiter():
    respx.get("https://solestop.com/products.json").respond(503, headers={"Retry-After": "120"})

    # The product lookup makes a new client per request, so two clients must share state.
    async with create_http_client() as first:
        assert (await first.get("https://solestop.com/products.json")).status_code == 503
    async with create_http_client() as second:
        with pytest.raises(StoreBusyError):
            await second.get("https://solestop.com/products.json")

    assert limiter.health("solestop.com").consecutive_errors == 1
    assert respx.calls.call_count == 1  # the second request never left


@respx.mock
async def test_a_redirect_to_www_counts_against_the_same_store():
    respx.get("https://foosh.ca/products/x.js").respond(
        301, headers={"Location": "https://www.foosh.ca/products/x.js"}
    )
    respx.get("https://www.foosh.ca/products/x.js").respond(429, headers={"Retry-After": "60"})

    async with create_http_client() as client:
        response = await client.get("https://foosh.ca/products/x.js")

    assert response.status_code == 429
    # The 429 came from www.foosh.ca, and it is foosh.ca's product pages that back off.
    health = limiter.health("foosh.ca", Endpoint.PRODUCT)
    assert health.consecutive_errors == 1
    assert health.retry_in_s > MAX_WAIT_S
    assert limiter.health("foosh.ca", Endpoint.CATALOG).consecutive_errors == 0


@respx.mock
async def test_connection_errors_reach_the_limiter_and_the_caller():
    respx.get("https://nrml.ca/products.json").mock(side_effect=httpx.ConnectError("boom"))

    async with create_http_client() as client:
        with pytest.raises(httpx.ConnectError):
            await client.get("https://nrml.ca/products.json")

    assert limiter.health("nrml.ca").consecutive_errors == 1


@respx.mock
async def test_the_catalog_keeps_working_while_product_pages_are_refused():
    respx.get("https://ca.kith.com/products/x.js").respond(429, headers={"Retry-After": "60"})
    respx.get("https://ca.kith.com/products.json").respond(json={"products": []})

    async with create_http_client() as client:
        assert (await client.get("https://ca.kith.com/products/x.js")).status_code == 429
        assert (await client.get("https://ca.kith.com/products.json")).status_code == 200
        with pytest.raises(StoreBusyError):
            await client.get("https://ca.kith.com/products/y.js")


@respx.mock
async def test_requests_say_who_we_are():
    route = respx.get("https://nrml.ca/products.json").respond(json={"products": []})

    async with create_http_client() as client:
        await client.get("https://nrml.ca/products.json")

    sent = route.calls.last.request.headers["user-agent"]
    assert sent == USER_AGENT
    assert sent.startswith("SiteMonitor/")
    assert "Mozilla" not in sent and "Chrome" not in sent
