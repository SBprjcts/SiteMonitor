import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router"
import { ExternalLink, Loader2, Search } from "lucide-react"
import { toast } from "sonner"

import type { EventType, ProductDetail } from "@/api/types"
import { EVENT_META } from "@/components/products/events"
import { ProductThumb } from "@/components/products/ProductThumb"
import { SizeGrid } from "@/components/products/SizeGrid"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { useCreateWatch, useLookupProduct } from "@/hooks/useWatches"
import { formatPrice } from "@/lib/format"
import { parseProductUrl } from "@/lib/shopify"

const PRODUCT_EVENTS: EventType[] = ["restock", "sold_out", "price_drop"]

export function ProductUrlWatchForm() {
  const [url, setUrl] = useState("")
  const [urlError, setUrlError] = useState<string | null>(null)
  const lookup = useLookupProduct()

  function onLookup(e: FormEvent) {
    e.preventDefault()
    if (!parseProductUrl(url)) {
      setUrlError("Paste a product link, like https://ca.kith.com/products/<handle>")
      return
    }
    setUrlError(null)
    lookup.mutate(url)
  }

  return (
    <div className="grid gap-6">
      <form onSubmit={onLookup} className="grid gap-2">
        <Label htmlFor="product-url">Product link</Label>
        <div className="flex gap-2">
          <Input
            id="product-url"
            placeholder="https://ca.kith.com/products/…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            aria-invalid={!!urlError}
            autoFocus
          />
          <Button type="submit" disabled={lookup.isPending}>
            {lookup.isPending ? <Loader2 className="animate-spin" /> : <Search />}
            Look up
          </Button>
        </div>
        {(urlError || lookup.error) && (
          <p className="text-sm text-destructive">{urlError ?? lookup.error?.message}</p>
        )}
      </form>

      {lookup.data && <WatchOptions key={lookup.data.id} product={lookup.data} />}
    </div>
  )
}

function WatchOptions({ product }: { product: ProductDetail }) {
  const navigate = useNavigate()
  const createWatch = useCreateWatch()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [events, setEvents] = useState<Set<EventType>>(new Set(["restock"]))
  const [maxPrice, setMaxPrice] = useState("")

  const soldOut = product.variants.filter((v) => !v.available)
  const inStockCount = product.variants.length - soldOut.length
  const price = product.variants[0]?.price_cents
  const maxPriceCents = maxPrice ? Math.round(Number(maxPrice) * 100) : null
  const maxPriceInvalid = maxPrice !== "" && (!Number.isFinite(maxPriceCents) || maxPriceCents! <= 0)

  function toggleSize(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleEvent(type: EventType, checked: boolean) {
    setEvents((prev) => {
      const next = new Set(prev)
      if (checked) next.add(type)
      else next.delete(type)
      return next
    })
  }

  function onSave() {
    createWatch.mutate(
      {
        type: "product",
        product_id: product.id,
        // No sizes selected means watch every size.
        sizes: selected.size ? [...selected] : null,
        event_types: [...events],
        max_price_cents: maxPriceCents,
      },
      {
        onSuccess: () => {
          toast.success(`Watching ${product.title}`)
          navigate("/watches")
        },
        onError: (err) => toast.error(`Couldn't save the watch: ${err.message}`),
      },
    )
  }

  return (
    <Card>
      <CardContent className="grid gap-6">
        <div className="flex gap-4">
          <ProductThumb src={product.image_url} />
          <div className="min-w-0">
            <div className="font-medium">{product.title}</div>
            <div className="text-sm text-muted-foreground">
              {product.store.name}
              {price !== undefined && <> · {formatPrice(price)}</>} · {inStockCount} of{" "}
              {product.variants.length} sizes in stock
            </div>
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

        <Separator />

        <section className="grid gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="font-medium">Sizes</h2>
              <p className="text-sm text-muted-foreground">
                {selected.size
                  ? `${selected.size} selected`
                  : "None selected: every size will be watched."}
              </p>
            </div>
            <div className="flex gap-1">
              <Button
                variant="ghost"
                size="sm"
                disabled={!soldOut.length}
                onClick={() => setSelected(new Set(soldOut.map((v) => v.external_id)))}
              >
                Sold-out sizes
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
                Clear
              </Button>
            </div>
          </div>
          <SizeGrid variants={product.variants} selected={selected} onToggle={toggleSize} />
        </section>

        <section className="grid gap-3">
          <h2 className="font-medium">Alert me on</h2>
          <div className="flex flex-wrap gap-x-6 gap-y-3">
            {PRODUCT_EVENTS.map((type) => (
              <Label key={type} className="flex items-center gap-2 font-normal">
                <Checkbox
                  checked={events.has(type)}
                  onCheckedChange={(checked) => toggleEvent(type, checked === true)}
                />
                {EVENT_META[type].label}
              </Label>
            ))}
          </div>
        </section>

        <section className="grid max-w-xs gap-2">
          <Label htmlFor="max-price">
            Max price (CAD) <span className="text-muted-foreground">(optional)</span>
          </Label>
          <Input
            id="max-price"
            type="number"
            inputMode="decimal"
            min="0"
            step="0.01"
            placeholder="No limit"
            value={maxPrice}
            onChange={(e) => setMaxPrice(e.target.value)}
            aria-invalid={maxPriceInvalid}
          />
          {maxPriceInvalid && <p className="text-sm text-destructive">Enter a positive amount.</p>}
        </section>

        <p className="text-sm text-muted-foreground">
          Alerts go to your default Discord webhook. Webhook settings are coming soon.
        </p>

        <div className="flex justify-end">
          <Button
            size="lg"
            onClick={onSave}
            disabled={!events.size || maxPriceInvalid || createWatch.isPending}
          >
            {createWatch.isPending && <Loader2 className="animate-spin" />}
            {selected.size ? `Watch ${selected.size} size${selected.size > 1 ? "s" : ""}` : "Watch all sizes"}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
