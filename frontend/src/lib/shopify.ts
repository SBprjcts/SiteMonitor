/**
 * Parses a Shopify product URL into its store domain and product handle.
 * Handles /products/<handle>, /collections/<c>/products/<handle>, query strings and .js/.json.
 */
export function parseProductUrl(input: string): { domain: string; handle: string } | null {
  const trimmed = input.trim()
  if (!trimmed) return null
  let url: URL
  try {
    url = new URL(trimmed.includes("://") ? trimmed : `https://${trimmed}`)
  } catch {
    return null
  }
  const match = url.pathname.match(/\/products\/([^/]+?)(?:\.(?:js|json))?\/?$/)
  if (!match || !url.hostname.includes(".")) return null
  return { domain: url.hostname.toLowerCase(), handle: decodeURIComponent(match[1]).toLowerCase() }
}

/** Shopify cart permalink: opens checkout with one of this size in the cart. */
export function cartUrl(domain: string, variantExternalId: string): string {
  return `https://${domain}/cart/${variantExternalId}:1`
}
