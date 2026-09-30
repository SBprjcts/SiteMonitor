// Typed API client. Each function calls the backend, or the in-memory mock when
// VITE_USE_MOCKS is not "false".

import { parseProductUrl } from "@/lib/shopify"

import { delay, mockDb, mockLookupProduct, mockNextId } from "./mock"
import type {
  NewProductWatch,
  ProductDetail,
  StockEvent,
  Store,
  Watch,
  WatchListItem,
} from "./types"

export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS !== "false"

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/**
 * FastAPI sends `detail` as a string for HTTPException, but as a list of issues for
 * request validation errors ("Value error, Enter the store's domain, not an IP address").
 */
function errorMessage(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string") {
    return detail[0].msg.replace(/^Value error, /, "")
  }
  return undefined
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, errorMessage(body?.detail) ?? res.statusText)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

// Stores

export function listStores(): Promise<Store[]> {
  if (USE_MOCKS) return delay(mockDb.stores)
  return request("/stores")
}

export function updateStore(id: number, patch: Pick<Store, "enabled">): Promise<Store> {
  if (USE_MOCKS) {
    const store = mockDb.stores.find((s) => s.id === id)
    if (!store) return Promise.reject(new ApiError(404, "Store not found"))
    Object.assign(store, patch)
    return delay(store)
  }
  return request(`/stores/${id}`, { method: "PATCH", body: JSON.stringify(patch) })
}

/** Adds a Shopify store. The backend validates it by probing /products.json. */
export function addStore(input: { domain: string; name?: string }): Promise<Store> {
  if (USE_MOCKS) return delay(null, 800).then(() => mockAddStore(input))
  return request("/stores", { method: "POST", body: JSON.stringify(input) })
}

function mockAddStore({ domain, name }: { domain: string; name?: string }): Store {
  if (mockDb.stores.some((s) => s.domain === domain)) {
    throw new ApiError(409, `${domain} is already being monitored`)
  }
  const store: Store = {
    id: Math.max(0, ...mockDb.stores.map((s) => s.id)) + 1,
    name: name || domain,
    domain,
    platform: "shopify",
    enabled: true,
    status: "ok",
    hot_interval_s: 15,
    sweep_interval_s: 60,
    last_ok_at: new Date().toISOString(),
    consecutive_errors: 0,
  }
  mockDb.stores.push(store)
  return store
}

// Products

/** Fetches a product by its store URL so the user can pick sizes to watch. */
export function lookupProduct(url: string): Promise<ProductDetail> {
  if (USE_MOCKS) return delay(null, 700).then(() => mockLookup(url))
  return request("/products/lookup", { method: "POST", body: JSON.stringify({ url }) })
}

function mockLookup(url: string): ProductDetail {
  const parsed = parseProductUrl(url)
  if (!parsed) throw new ApiError(422, "That doesn't look like a Shopify product link")
  const store = mockDb.stores.find((s) => s.domain === parsed.domain)
  if (!store) {
    throw new ApiError(404, `${parsed.domain} isn't a monitored store yet. Add it on the Stores page.`)
  }
  if (store.platform !== "shopify") {
    throw new ApiError(422, `${store.name} isn't supported yet`)
  }
  return { ...mockLookupProduct(store, parsed.handle), store }
}

function mockProductDetail(id: number): ProductDetail {
  const product = mockDb.products.find((p) => p.id === id)
  const store = product && mockDb.stores.find((s) => s.id === product.store_id)
  if (!product || !store) throw new ApiError(404, "Product not found")
  return { ...product, store }
}

export function getProduct(id: number): Promise<ProductDetail> {
  if (USE_MOCKS) return delay(null).then(() => mockProductDetail(id))
  return request(`/products/${id}`)
}

/** Newest first. */
export function listProductEvents(productId: number): Promise<StockEvent[]> {
  if (USE_MOCKS) {
    const events = mockDb.events
      .filter((e) => e.product_id === productId)
      .sort((a, b) => b.occurred_at.localeCompare(a.occurred_at))
    return delay(events)
  }
  return request(`/products/${productId}/events`)
}

// Watches

export function listWatches(): Promise<WatchListItem[]> {
  if (USE_MOCKS) {
    const items = mockDb.watches
      .map((w) => ({ ...w, product: w.product_id ? mockProductDetail(w.product_id) : null }))
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
    return delay(items)
  }
  return request("/watches")
}

export function createWatch(input: NewProductWatch): Promise<Watch> {
  if (USE_MOCKS) {
    const watch: Watch = {
      id: mockNextId(),
      query: null,
      keywords_pos: [],
      keywords_neg: [],
      store_ids: null,
      webhook_id: null,
      active: true,
      created_at: new Date().toISOString(),
      ...input,
    }
    mockDb.watches.push(watch)
    return delay(watch)
  }
  return request("/watches", { method: "POST", body: JSON.stringify(input) })
}

export function updateWatch(id: number, patch: Pick<Watch, "active">): Promise<Watch> {
  if (USE_MOCKS) {
    const watch = mockDb.watches.find((w) => w.id === id)
    if (!watch) return Promise.reject(new ApiError(404, "Watch not found"))
    Object.assign(watch, patch)
    return delay(watch)
  }
  return request(`/watches/${id}`, { method: "PATCH", body: JSON.stringify(patch) })
}

export function deleteWatch(id: number): Promise<void> {
  if (USE_MOCKS) {
    mockDb.watches = mockDb.watches.filter((w) => w.id !== id)
    return delay(undefined)
  }
  return request(`/watches/${id}`, { method: "DELETE" })
}
