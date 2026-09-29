// Hand-written API types mirroring the data model in CLAUDE.md.
// Field names are snake_case to match FastAPI's JSON, so swapping these for the
// generated `schema.d.ts` types later is a rename, not a rewrite.

export type StoreStatus = "ok" | "degraded" | "blocked"
export type StorePlatform = "shopify" | "shopify_hydrogen"

export interface Store {
  id: number
  name: string
  domain: string
  platform: StorePlatform
  enabled: boolean
  status: StoreStatus
  hot_interval_s: number
  sweep_interval_s: number
  last_ok_at: string | null
  consecutive_errors: number
}

export interface Variant {
  id: number
  external_id: string
  size: string
  sku: string | null
  price_cents: number
  available: boolean
  updated_at: string
}

export interface Product {
  id: number
  store_id: number
  external_id: string
  handle: string
  title: string
  vendor: string | null
  image_url: string | null
  url: string
  first_seen_at: string
  last_seen_at: string
  variants: Variant[]
}

export type EventType = "restock" | "sold_out" | "price_drop" | "new_product"

export interface StockEvent {
  id: number
  store_id: number
  product_id: number
  variant_id: number | null
  type: EventType
  old_value: string | null
  new_value: string | null
  occurred_at: string
}

export type WatchType = "product" | "style_code" | "keyword"

export interface Watch {
  id: number
  type: WatchType
  product_id: number | null
  query: string | null
  keywords_pos: string[]
  keywords_neg: string[]
  /** null means all stores */
  store_ids: number[] | null
  /** Variant external ids; null means all sizes */
  sizes: string[] | null
  event_types: EventType[]
  max_price_cents: number | null
  webhook_id: number | null
  active: boolean
  created_at: string
}

/** GET /products/:id and POST /products/lookup return the product with its store. */
export interface ProductDetail extends Product {
  store: Store
}

/** GET /watches embeds the watched product (null for style-code/keyword watches). */
export interface WatchListItem extends Watch {
  product: ProductDetail | null
}

export interface NewProductWatch {
  type: "product"
  product_id: number
  sizes: string[] | null
  event_types: EventType[]
  max_price_cents: number | null
}
