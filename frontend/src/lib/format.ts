const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" })

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
  ["second", 1],
]

/** "12 seconds ago", "3 hours ago", ... */
export function formatRelativeTime(iso: string, now = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000)
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size || unit === "second") {
      return relative.format(Math.round(seconds / size), unit)
    }
  }
  return ""
}

const cad = new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" })

export function formatPrice(cents: number): string {
  return cad.format(cents / 100)
}

/**
 * Accepts a pasted store URL or domain ("https://www.kith.com/collections/x") and returns
 * the bare hostname without "www." ("kith.com"), or null if it isn't a domain.
 * Mirrors normalize_domain() in backend/app/stores/domain.py: both sides must agree,
 * or the same store could be added twice.
 */
export function normalizeDomain(input: string): string | null {
  const trimmed = input.trim().toLowerCase()
  if (!trimmed) return null
  let hostname: string
  try {
    hostname = new URL(trimmed.includes("://") ? trimmed : `https://${trimmed}`).hostname
  } catch {
    return null
  }
  // IPv6 hostnames have no dots, so this also rejects them.
  if (!hostname.includes(".") || /^\d+(\.\d+){3}$/.test(hostname)) return null
  return stripWww(hostname)
}

/** "www.nrml.ca" -> "nrml.ca", but "www.com" stays as is. */
export function stripWww(hostname: string): string {
  return hostname.startsWith("www.") && hostname.slice(4).includes(".")
    ? hostname.slice(4)
    : hostname
}
