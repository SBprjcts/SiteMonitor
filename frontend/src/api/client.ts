// Typed API client. Each function calls the backend, or the in-memory mock when
// VITE_USE_MOCKS is not "false".

import { delay, mockDb } from "./mock"
import type { Store } from "./types"

export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS !== "false"

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.detail ?? res.statusText)
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
