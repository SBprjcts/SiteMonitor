# SiteMonitor

SiteMonitor is a restock monitor for Canadian sneaker boutiques that run on Shopify. It watches products, style codes, and keyword sets across stores. When something changes, it sends a Discord webhook alert with a one-click checkout link and records the event for history and analytics. It is built by two collaborators who both work full-stack.

This file is the source of truth for architecture and conventions. If you change a decision here, update this file in the same PR.

## Goals and non-goals

**Goals**
- Detect restocks, sellouts, price drops, and new product matches quickly (target: under 30 seconds from the store change to the Discord alert).
- Alert with a direct cart link: `https://{domain}/cart/{variant_id}:1`. This is Shopify's standard cart permalink, and it lets the user check out in one click.
- Keep a full event history so we can report metrics such as detection latency and sellout speed by size.
- Support multiple users, each with their own watches and webhooks.
- Run locally now and on a VPS later **with no rewrite**.

**Non-goals (do not build)**
- Automated checkout, add-to-cart bots, or captcha solving.
- Anti-bot evasion (rotating fingerprints, bypassing Cloudflare challenges). If a store blocks us, back off and mark it degraded.
- Scraping HTML when a JSON endpoint exists.

## How Shopify data is fetched

| Endpoint | Returns | Used by |
|---|---|---|
| `https://{domain}/products/{handle}.js` | One product with every variant (size), `available`, price (in cents), and images | **Hot loop** for products users watch |
| `https://{domain}/products.json?limit=250&page=N` | The catalog: products, variants (`available`, `price` as a string in dollars), tags, `body_html` | **Sweep loop** for new products, style codes, and keywords |
| `https://{domain}/cart/{variant_id}:1` | Cart permalink | The link in every alert |

Notes:
- The variant `sku` is **not** the style code. On Kith, for example, it is an internal number (`2000428323`). Style codes appear in the title, handle, tags, or `body_html`, so match across all of those fields.
- Prices differ between the two endpoints: `.js` gives integer cents, while `products.json` gives a dollar string. The adapter normalizes both to `price_cents: int`. All stores are CAD.

## Architecture

```
React dashboard ──REST + SSE──► FastAPI (app/api)
                                     │
                                     ▼
                              SQLite / Postgres ◄──── Monitor (app/monitor)
                                                       scheduler
                                                         → per-domain rate limiter
                                                         → adapter (Shopify)
                                                         → diff engine → events
                                                         → matcher → alerts
                                                         → notifier ──► Discord webhooks
```

### Process model
- **Locally, everything is one process.** FastAPI's lifespan starts the monitor as background asyncio tasks when `MONITOR_ENABLED=true`. FastAPI also serves the built frontend, so the whole app lives at `http://localhost:8000`.
- **The code is ready to split.** `app/monitor/` and `app/notifier/` must **never import from `app/api/`**. The monitor must be runnable on its own with `python -m app.monitor`. On the VPS, the API and the monitor can then run as separate containers against the same DB.

### Shared fetching, per-user watching
- `stores`, `products`, `variants`, and `events` are **global**. Each product is fetched once, no matter how many users watch it.
- `watches`, `webhooks`, and `alerts` belong to a user.
- This is the key scaling property: 50 users watching the same Kith shoe still means one request to Kith.

### Polling loops (per store)
1. **Hot loop** (default every 15s): fetches `/products/{handle}.js` for each product that has at least one active product watch.
2. **Sweep loop** (default every 60s): fetches the first page of `/products.json?limit=250`, which covers recently added and updated products. It upserts the products, runs the diff, and feeds style-code and keyword matching. Deeper pages are fetched on a slower cadence (default every 30 min).

Intervals are configurable per store.

### Per-domain rate limiter (`monitor/ratelimit.py`)
- A token bucket per domain (default about 1 request every 2 seconds) with random jitter. All loops for a domain share the same bucket.
- On 429 or 5xx responses: exponential backoff, and honor `Retry-After` when the store sends it. Solestop, for example, returns intermittent 503s.
- A circuit breaker: after N consecutive failures the store is marked `degraded` and polled slowly until it recovers. Store health (`last_ok_at`, `consecutive_errors`, `status`) is visible in the UI.
- Send a normal browser User-Agent. Never parallelize requests to the same domain.

### Diff engine (`monitor/diff.py`)
Compares the freshly fetched variant state with the stored state and emits `events`:

| Event | Condition |
|---|---|
| `restock` | variant `available` goes from false to true |
| `sold_out` | variant `available` goes from true to false |
| `price_drop` | variant `price_cents` decreases |
| `new_product` | product id never seen before for this store |

- **The first sighting of a product is a baseline.** It emits only `new_product` and never a burst of `restock` events.
- A product that disappears from the catalog is marked `last_seen_at` and never deleted.
- The diff engine is pure (it takes old and new state and returns events), which makes it easy to unit test.

### Matcher (`monitor/matching.py`)
Routes each event to the active watches that match it:

- **Product watch:** `product_id` matches, the variant passes the size filter, and the event type is enabled on the watch.
- **Style-code watch:** normalize both sides (lowercase, remove `-` and whitespace, e.g. `DD1391-100` → `dd1391100`) and search the product's `search_text`, which is built from the title, handle, tags, `body_html` stripped of tags, and variant SKUs, all normalized.
- **Keyword watch:** input is comma-separated, and a `-` prefix marks a negative. For example, `nike, low, panda, -gs, -kids` means **every** positive keyword must match as a whole word and **any** negative excludes the product. Matching is case-insensitive.
- Optional filters on all watch types: a store subset (null means all stores), sizes, and `max_price_cents`.

### Notifier (`app/notifier/`)
- An async queue, so a slow Discord request never blocks polling.
- **One embed per product per poll cycle.** If 8 sizes restock at once, that is one message listing the sizes, each with its own ATC link, not 8 messages.
- Embed fields: product image, title, store, event type, sizes, CAD price (with the old price for price drops), product link, per-size ATC links, and the optional role ping (`<@&role_id>`).
- Respect Discord webhook rate limits (retry on 429 using `retry_after`).
- Dedupe with a unique constraint on `alerts(watch_id, event_id)`, plus a per-variant cooldown (default 5 min) so flickering stock does not spam.
- Every send is recorded in `alerts` with its status or error.

### Adapters (`monitor/adapters/`)
```python
class StoreAdapter(Protocol):
    async def fetch_product(self, domain: str, handle: str) -> ProductData: ...
    async def fetch_catalog_page(self, domain: str, page: int) -> list[ProductData]: ...
```
Adapters return normalized `ProductData`/`VariantData` (pydantic) objects and know nothing about the DB, so they take a plain `domain`, not a `Store` row. All requests go through the shared client from `monitor/http.py`.
- `shopify.py`: the only adapter for now.
- `shopify_hydrogen.py` (later): for headless Shopify stores like Haven, via the public Storefront API.
- `amazon.py` (much later).

### Live updates
`GET /api/stream` is a Server-Sent Events stream that pushes new events and alerts to the dashboard.

## Tech stack

**Backend** (`backend/`)
- Python 3.12, managed with **uv**
- FastAPI, uvicorn
- httpx (async) for all outbound requests
- SQLAlchemy 2 (async) + Alembic. Uses SQLite locally (aiosqlite, WAL mode) and Postgres optionally on the VPS (asyncpg), switched by `DATABASE_URL`. **Keep queries dialect-neutral.** No SQLite-only or Postgres-only SQL.
- pydantic v2 + pydantic-settings for config
- Auth: email + password hashed with argon2, server-side sessions in an httpOnly cookie
- Tests: pytest, pytest-asyncio, respx (to mock httpx)
- Lint and format: ruff

**Frontend** (`frontend/`)
- Vite + React + TypeScript (strict), linted with oxlint
- Tailwind CSS + shadcn/ui, with a **dark theme by default**
- TanStack Query for server state, React Router for routing
- Recharts for charts
- API types generated from FastAPI's OpenAPI schema with `openapi-typescript` (`npm run gen:api` → `src/api/schema.d.ts`). **This generated file is the contract between frontend and backend.** Regenerate it whenever an endpoint changes, and commit it in the same PR.

## Repo layout

```
backend/
  pyproject.toml
  alembic/                  migrations
  app/
    main.py                 app factory, lifespan (starts monitor), static frontend
    config.py               Settings (pydantic-settings, reads .env)
    db/
      models.py             SQLAlchemy models
      session.py            engine + session factory
    schemas/                pydantic request/response models
    api/                    routers: auth, stores, watches, products, events, webhooks, stream
    monitor/
      __main__.py           run the monitor standalone
      scheduler.py          hot + sweep loops per store
      ratelimit.py          per-domain token bucket, backoff, circuit breaker
      diff.py               pure state diff → events
      matching.py           style-code/keyword normalization + watch matching
      adapters/
        base.py             StoreAdapter protocol, ProductData/VariantData
        shopify.py
    notifier/
      discord.py            embed builder + sender
      queue.py
    seed.py                 seeds the store list below
  tests/
    fixtures/               recorded store JSON (never hit live stores in tests)
frontend/
  src/
    api/                    generated schema + fetch client
    pages/
    components/
    hooks/
docker-compose.yml          (phase 5)
.env.example
run.ps1                     one-command local start on Windows
```

## Data model

| Table | Key columns |
|---|---|
| `users` | id, email (unique), password_hash, created_at |
| `sessions` | id (token), user_id, expires_at |
| `stores` | id, name, domain (unique), platform (`shopify` \| `shopify_hydrogen`), enabled, hot_interval_s, sweep_interval_s, status (`ok` \| `degraded` \| `blocked`), last_ok_at, consecutive_errors |
| `products` | id, store_id, external_id, handle, title, vendor, image_url, url, search_text, first_seen_at, last_seen_at. Unique on (store_id, external_id) |
| `variants` | id, product_id, external_id, size, sku, price_cents, available, updated_at. Unique on (product_id, external_id) |
| `events` | id, store_id, product_id, variant_id (nullable), type, old_value, new_value, occurred_at |
| `watches` | id, user_id, type (`product` \| `style_code` \| `keyword`), product_id (nullable), query, keywords_pos (json), keywords_neg (json), store_ids (json, null means all), sizes (json, null means all), event_types (json), max_price_cents (nullable), webhook_id, active, created_at |
| `webhooks` | id, user_id, name, url, role_id (nullable) |
| `alerts` | id, watch_id, event_id, webhook_id, status (`queued` \| `sent` \| `failed`), sent_at, error. Unique on (watch_id, event_id) |

All timestamps are stored as UTC. Store money in cents as integers, never as floats.

## Seeded stores (verified 2026-09-28)

All of these return valid `products.json`:

| Store | Domain |
|---|---|
| Kith Canada | `ca.kith.com` |
| Momentum | `momentumshop.ca` |
| NRML | `nrml.ca` |
| Foosh | `foosh.ca` |
| Qlassic | `qlassic.ca` |
| Courtside Sneakers | `courtsidesneakers.com` |
| Sneakerbox | `sneakerboxshop.ca` |
| Lessoneseven | `lessoneseven.com` |
| Solestop | `solestop.com` (intermittent 503s, so backoff is required) |
| JD Sports Canada | `jdsports.ca` |
| Livestock | `deadstock.ca` |
| BB Branded | `bbbranded.com` |

**Not yet supported:** Haven (`havenshop.com`) runs headless Shopify (Hydrogen). `products.json` returns an empty list and `.js` returns 404. It needs the `shopify_hydrogen` adapter (phase 6).

Users can add any other Shopify store in the UI. The backend validates it by requesting `/products.json?limit=1` and checking for a `products` key.

## Dashboard pages

- **Login / Register**
- **Dashboard:** live event feed (SSE), quick stats (active watches, alerts today, store health)
- **Watches:** list, pause/resume, delete. The "Add watch" flow has three tabs:
  1. **Product URL:** paste a link. The backend fetches it and shows a size grid with current stock, and the user ticks the sizes to watch.
  2. **Style code:** e.g. `DD1391-100`, with a store filter.
  3. **Keywords:** e.g. `nike, low, panda, -gs, -kids`, with a live preview of matching products already in the DB.

  In all three tabs the user picks the event types, a webhook, and optionally a max price.
- **Product detail:** size-by-size stock grid, event timeline, time-to-sellout per size
- **Stores:** health status, enable/disable, add a custom Shopify store
- **Settings:** manage Discord webhooks, with a "Send test alert" button
- **Analytics** (later): restocks per store, sellout speed by size, detection latency

## Build phases

1. **Engine:** Shopify adapter, diff engine, models, SQLite, and a CLI that prints changes for one product. Fixture tests. *Pair on this: both later phases depend on it.*
2. **Alerts and scale:** rate limiter, scheduler (hot and sweep loops), Discord notifier, and seeding every store.
3. **API and dashboard:** auth, stores, product URL watches with the size picker, live feed, webhook settings.
4. **Matching:** style-code and keyword watches, new-product and price-drop alerts.
5. **Deploy and polish:** Docker Compose, VPS deploy behind Caddy (automatic HTTPS), GitHub Actions CI, README with an architecture diagram and real metrics.
6. **Expansion:** Hydrogen adapter (Haven), Amazon adapter, and a desktop wrapper or browser extension as a thin client over the same backend.

## Feature slices (for splitting work)

Each slice is end to end: backend, API, UI, and tests. Claim a slice by assigning its GitHub issue to yourself.

| Slice | Scope |
|---|---|
| A. Stores | store CRUD, validation probe, health tracking, Stores page |
| B. Product watches | URL → size picker, restock/sold-out alerts, Product detail page |
| C. Style code + keywords | normalization, matcher, keyword preview, new-product alerts |
| D. Notifier + webhooks | Discord embeds, queue, dedupe/cooldown, Settings page, test alert |
| E. Auth | register/login/logout, sessions, per-user scoping on every query |
| F. Feed + analytics | SSE stream, Dashboard feed, charts |
| G. Price drops | price diff events, alert formatting |

## Workflow

- `main` is protected. Every change goes through a PR with **one approving review** from the other collaborator.
- Short-lived branches: `feat/<slice>-<thing>`, `fix/<thing>`, `chore/<thing>`.
- Commit messages follow Conventional Commits (`feat: add shopify adapter`). Do not add AI attribution trailers or mentions to commits or PRs.
- Track work in GitHub Issues and the Projects board (To Do / In Progress / In Review / Done).
- CI (phase 5) runs `ruff check`, `ruff format --check`, `pytest`, `npm run typecheck`, and `npm run lint` (oxlint). A PR must be green before merging.

## Rules

- **Never commit `.env`** or real webhook URLs. Add new settings to `.env.example` with a placeholder.
- **Tests never hit live stores or Discord.** Use recorded JSON in `backend/tests/fixtures/` and mock with respx.
- Every user-owned query must filter by `user_id`. There must be no cross-user data leaks.
- All outbound HTTP to stores goes through the rate limiter. No direct `httpx.get` in feature code.
- Monitor code must not import API code (see Process model).
- Schema changes require an Alembic migration in the same PR.
- Relationships are `lazy="raise"`: load them explicitly with `selectinload()` in the query, or accessing them raises.
- Both collaborators work on Windows. Scripts and docs use PowerShell-friendly commands, and paths are handled with `pathlib`.

## Common commands

```powershell
# backend
cd backend
uv sync                                   # install deps
uv run alembic upgrade head               # migrate DB
uv run python -m app.seed                 # seed stores
uv run uvicorn app.main:app --reload      # API + monitor on :8000
uv run python -m app.monitor              # monitor only
uv run pytest                             # tests
uv run ruff check . ; uv run ruff format .

# frontend
cd frontend
npm install
npm run dev                               # Vite on :5173, proxies /api to :8000
npm run gen:api                           # regenerate API types from http://localhost:8000/openapi.json
npm run build                             # output served by FastAPI

# everything at once
./run.ps1
```

## Configuration (`.env`)

| Var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `backend/sitemonitor.db` (absolute path, so it does not depend on the current folder) | Postgres on the VPS if desired |
| `MONITOR_ENABLED` | `true` | Run the monitor inside the API process |
| `DEFAULT_HOT_INTERVAL_S` | `15` | Product watch poll interval |
| `DEFAULT_SWEEP_INTERVAL_S` | `60` | Catalog sweep interval |
| `DOMAIN_MIN_REQUEST_GAP_S` | `2` | Rate limiter spacing per domain |
| `ALERT_COOLDOWN_S` | `300` | Per-variant alert cooldown |
| `SESSION_SECRET` | *(required)* | Session signing |
| `LOG_LEVEL` | `INFO` | |
