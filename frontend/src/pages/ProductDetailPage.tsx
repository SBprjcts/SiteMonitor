import { Link, useParams } from "react-router"
import { ArrowLeft, ExternalLink } from "lucide-react"

import type { ProductDetail, StockEvent } from "@/api/types"
import { PageHeader } from "@/components/layout/PageHeader"
import { EVENT_META } from "@/components/products/events"
import { ProductThumb } from "@/components/products/ProductThumb"
import { SizeGrid } from "@/components/products/SizeGrid"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useProduct, useProductEvents } from "@/hooks/useWatches"
import { formatPrice, formatRelativeTime } from "@/lib/format"
import { cartUrl } from "@/lib/shopify"
import { cn } from "@/lib/utils"

export function ProductDetailPage() {
  const id = Number(useParams().id)
  const { data: product, isPending, error } = useProduct(id)

  if (error) {
    return (
      <>
        <PageHeader title="Product not found" description={error.message} />
        <Button asChild variant="outline">
          <Link to="/watches">
            <ArrowLeft />
            Back to watches
          </Link>
        </Button>
      </>
    )
  }

  if (isPending) {
    return (
      <div className="grid gap-4">
        <Skeleton className="h-16 w-2/3" />
        <Skeleton className="h-48 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    )
  }

  const inStock = product.variants.filter((v) => v.available).length
  const price = product.variants[0]?.price_cents

  return (
    <>
      <Link
        to="/watches"
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Watches
      </Link>

      <div className="mb-6 flex items-center gap-4">
        <ProductThumb src={product.image_url} className="size-20" />
        <div className="min-w-0">
          <h1 className="font-heading text-2xl font-semibold tracking-tight">{product.title}</h1>
          <p className="text-sm text-muted-foreground">
            {product.store.name}
            {price !== undefined && <> · {formatPrice(price)}</>} · {inStock} of{" "}
            {product.variants.length} sizes in stock
          </p>
          <a
            href={product.url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            View on store <ExternalLink className="size-3" />
          </a>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <Card>
          <CardHeader>
            <CardTitle>Stock by size</CardTitle>
            <p className="text-sm text-muted-foreground">
              Click an in-stock size to open checkout with it in your cart.
            </p>
          </CardHeader>
          <CardContent>
            <SizeGrid
              variants={product.variants}
              hrefFor={(v) => cartUrl(product.store.domain, v.external_id)}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>History</CardTitle>
          </CardHeader>
          <CardContent>
            <EventTimeline product={product} />
          </CardContent>
        </Card>
      </div>
    </>
  )
}

function describeEvent(event: StockEvent, product: ProductDetail): string {
  const size = product.variants.find((v) => v.id === event.variant_id)?.size
  if (event.type === "price_drop" && event.old_value && event.new_value) {
    return `${formatPrice(Number(event.old_value))} → ${formatPrice(Number(event.new_value))}`
  }
  return size ? `Size ${size}` : ""
}

function EventTimeline({ product }: { product: ProductDetail }) {
  const { data: events, isPending, error } = useProductEvents(product.id)

  if (error) return <p className="text-sm text-destructive">Couldn&apos;t load history.</p>
  if (isPending) return <Skeleton className="h-40 w-full" />
  if (!events.length) return <p className="text-sm text-muted-foreground">No changes seen yet.</p>

  return (
    <ol className="grid gap-4">
      {events.map((event) => {
        const { label, icon: Icon, color } = EVENT_META[event.type]
        return (
          <li key={event.id} className="flex items-start gap-3">
            <Icon className={cn("mt-0.5 size-4 shrink-0", color)} />
            <div className="min-w-0 flex-1 text-sm">
              <span className="font-medium">{label}</span>{" "}
              <span className="text-muted-foreground">{describeEvent(event, product)}</span>
            </div>
            <time
              dateTime={event.occurred_at}
              title={new Date(event.occurred_at).toLocaleString()}
              className="shrink-0 text-xs text-muted-foreground"
            >
              {formatRelativeTime(event.occurred_at)}
            </time>
          </li>
        )
      })}
    </ol>
  )
}
