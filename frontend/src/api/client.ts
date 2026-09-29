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
