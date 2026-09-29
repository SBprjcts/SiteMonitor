// In-memory mock backend used while the real API is being built.
// Everything here is fake data; delete this file once the backend endpoints exist.

import type { Store } from "./types"

const now = new Date().toISOString()

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
    last_ok_at: now,
    consecutive_errors: 0,
    ...overrides,
  }
}

export const mockDb = {
  stores: [
    store(1, "Kith Canada", "ca.kith.com"),
    store(2, "Momentum", "momentumshop.ca"),
    store(3, "NRML", "nrml.ca"),
    store(4, "Foosh", "foosh.ca"),
    store(5, "Qlassic", "qlassic.ca"),
    store(6, "Courtside Sneakers", "courtsidesneakers.com"),
    store(7, "Sneakerbox", "sneakerboxshop.ca"),
    store(8, "Lessoneseven", "lessoneseven.com"),
    store(9, "Solestop", "solestop.com", { status: "degraded", consecutive_errors: 3 }),
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
