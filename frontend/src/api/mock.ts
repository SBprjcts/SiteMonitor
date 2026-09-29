// In-memory mock backend used while the real API is being built.
// Everything here is fake data; delete this file once the backend endpoints exist.

import type { Product, StockEvent, Store, Variant, Watch } from "./types"

function secondsAgo(seconds: number): string {
  return new Date(Date.now() - seconds * 1000).toISOString()
}

function store(id: number, name: string, domain: string, overrides: Partial<Store> = {}): Store {
  return {
    id,
    name,
    domain,
    platform: "shopify",
    enabled: true,
    status: "ok",
    hot_interval_s: 15,
    sweep_interval_s: 60,
    last_ok_at: secondsAgo(3 + ((id * 7) % 15)),
    consecutive_errors: 0,
    ...overrides,
  }
}

export const mockDb = {
  products: [] as Product[],
  events: [] as StockEvent[],
  watches: [] as Watch[],
  stores: [
    store(1, "Kith Canada", "ca.kith.com"),
    store(2, "Momentum", "momentumshop.ca"),
    store(3, "NRML", "nrml.ca"),
    store(4, "Foosh", "foosh.ca"),
    store(5, "Qlassic", "qlassic.ca"),
    store(6, "Courtside Sneakers", "courtsidesneakers.com"),
    store(7, "Sneakerbox", "sneakerboxshop.ca"),
    store(8, "Lessoneseven", "lessoneseven.com"),
    store(9, "Solestop", "solestop.com", {
      status: "degraded",
      consecutive_errors: 3,
      last_ok_at: secondsAgo(190),
    }),
    store(10, "JD Sports Canada", "jdsports.ca"),
    store(11, "Livestock", "deadstock.ca"),
    store(12, "BB Branded", "bbbranded.com"),
    store(13, "Haven", "havenshop.com", {
      platform: "shopify_hydrogen",
      enabled: false,
      last_ok_at: null,
    }),
  ] as Store[],
}

/** Simulates network latency so loading states are visible during development. */
export function delay<T>(value: T, ms = 300): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), ms))
}

// Products

let nextId = 1000

/** Deterministic pseudo-random number in [0, 1) derived from a string. */
function seeded(key: string): number {
  let h = 2166136261
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return (h >>> 0) / 2 ** 32
}

const SIZES = ["7", "7.5", "8", "8.5", "9", "9.5", "10", "10.5", "11", "11.5", "12", "13"]

function titleFromHandle(handle: string): string {
  return handle
    .split("-")
    .filter(Boolean)
    .map((word) => (/\d/.test(word) ? word.toUpperCase() : word[0].toUpperCase() + word.slice(1)))
    .join(" ")
}

/**
 * Builds a believable product for any handle, with sizes, stock and a few past
 * events, so the watch flow can be exercised with any pasted URL.
 */
export function mockLookupProduct(store: Store, handle: string): Product {
  const existing = mockDb.products.find((p) => p.store_id === store.id && p.handle === handle)
  if (existing) return existing

  const productId = nextId++
  const basePrice = 14000 + Math.floor(seeded(handle) * 12) * 1000
  const variants: Variant[] = SIZES.map((size) => ({
    id: nextId++,
    external_id: String(40000000000000 + Math.floor(seeded(handle + size) * 1e12)),
    size,
    sku: null,
    price_cents: basePrice,
    available: seeded(`${handle}:${size}:stock`) > 0.55,
    updated_at: secondsAgo(30),
  }))

  const product: Product = {
    id: productId,
    store_id: store.id,
    external_id: String(8000000000000 + Math.floor(seeded(handle) * 1e12)),
    handle,
    title: titleFromHandle(handle),
    vendor: titleFromHandle(handle.split("-")[0] ?? "") || null,
    image_url: null,
    url: `https://${store.domain}/products/${handle}`,
    first_seen_at: secondsAgo(6 * 86_400),
    last_seen_at: secondsAgo(20),
    variants,
  }
  mockDb.products.push(product)

  // A short history: restocks and sellouts over the last few days, plus one price drop.
  variants.forEach((variant, i) => {
    if (seeded(`${handle}:${i}:event`) < 0.5) return
    const restock = variant.available
    mockDb.events.push({
      id: nextId++,
      store_id: store.id,
      product_id: productId,
      variant_id: variant.id,
      type: restock ? "restock" : "sold_out",
      old_value: String(!restock),
      new_value: String(restock),
      occurred_at: secondsAgo(Math.floor(seeded(`${handle}:${i}:when`) * 3 * 86_400)),
    })
  })
  mockDb.events.push({
    id: nextId++,
    store_id: store.id,
    product_id: productId,
    variant_id: null,
    type: "price_drop",
    old_value: String(basePrice + 3000),
    new_value: String(basePrice),
    occurred_at: secondsAgo(4 * 86_400),
  })
  return product
}

// One sample watch so the watch list isn't empty on first load.
const sampleProduct = mockLookupProduct(
  mockDb.stores[0],
  "nike-dunk-low-retro-white-black-dd1391-100",
)
mockDb.watches.push({
  id: nextId++,
  type: "product",
  product_id: sampleProduct.id,
  query: null,
  keywords_pos: [],
  keywords_neg: [],
  store_ids: null,
  sizes: sampleProduct.variants.slice(4, 7).map((v) => v.external_id),
  event_types: ["restock", "price_drop"],
  max_price_cents: null,
  webhook_id: null,
  active: true,
  created_at: secondsAgo(86_400),
})

export function mockNextId(): number {
  return nextId++
}
