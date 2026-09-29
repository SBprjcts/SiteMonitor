import { Link } from "react-router"
import { Eye, Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"

import type { WatchListItem } from "@/api/types"
import { PageHeader } from "@/components/layout/PageHeader"
import { EVENT_META } from "@/components/products/events"
import { ProductThumb } from "@/components/products/ProductThumb"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { useDeleteWatch, useToggleWatch, useWatches } from "@/hooks/useWatches"
import { formatPrice } from "@/lib/format"
import { cn } from "@/lib/utils"

export function WatchesPage() {
  const { data: watches, isPending, error, refetch } = useWatches()

  return (
    <>
      <PageHeader
        title="Watches"
        description="Products, style codes and keywords you are watching."
        actions={
          <Button asChild>
            <Link to="/watches/new">
              <Plus />
              New watch
            </Link>
          </Button>
        }
      />

      {error ? (
        <Card className="flex flex-col items-center gap-3 py-10 text-sm">
          <p className="text-destructive">Couldn&apos;t load watches: {error.message}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try again
          </Button>
        </Card>
      ) : isPending ? (
        <div className="grid gap-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
      ) : watches.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <Eye className="size-8 text-muted-foreground" />
            <div>
              <p className="font-medium">No watches yet</p>
              <p className="text-sm text-muted-foreground">
                Paste a product link and pick your sizes to get restock alerts.
              </p>
            </div>
            <Button asChild>
              <Link to="/watches/new">Add your first watch</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {watches.map((watch) => (
            <WatchRow key={watch.id} watch={watch} />
          ))}
        </div>
      )}
    </>
  )
}

function sizesSummary(watch: WatchListItem): string {
  if (!watch.sizes) return "All sizes"
  const labels = watch.product?.variants
    .filter((v) => watch.sizes!.includes(v.external_id))
    .map((v) => v.size)
  return labels?.length ? `Size ${labels.join(", ")}` : `${watch.sizes.length} sizes`
}

function WatchRow({ watch }: { watch: WatchListItem }) {
  const toggle = useToggleWatch()
  const remove = useDeleteWatch()
  const product = watch.product

  const title = product?.title ?? watch.query ?? "Untitled watch"

  return (
    <Card className={cn("py-0 transition-opacity", !watch.active && "opacity-60")}>
      <CardContent className="flex items-center gap-4 p-4">
        <ProductThumb src={product?.image_url ?? null} />
        <div className="min-w-0 flex-1">
          {product ? (
            <Link to={`/products/${product.id}`} className="font-medium hover:underline">
              {title}
            </Link>
          ) : (
            <span className="font-medium">{title}</span>
          )}
          <div className="truncate text-sm text-muted-foreground">
            {product?.store.name} · {sizesSummary(watch)}
            {watch.max_price_cents !== null && <> · under {formatPrice(watch.max_price_cents)}</>}
          </div>
          <div className="mt-2 flex flex-wrap gap-1">
            {watch.event_types.map((type) => (
              <Badge key={type} variant="secondary">
                {EVENT_META[type].label}
              </Badge>
            ))}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-3 sm:flex-row sm:items-center">
          <Switch
            checked={watch.active}
            onCheckedChange={(active) =>
              toggle.mutate(
                { id: watch.id, active },
                { onError: (err) => toast.error(`Couldn't update the watch: ${err.message}`) },
              )
            }
            aria-label={watch.active ? "Pause watch" : "Resume watch"}
          />
          <Button
            variant="ghost"
            size="icon"
            aria-label="Delete watch"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(watch.id, {
                onSuccess: () => toast.success("Watch deleted"),
                onError: (err) => toast.error(`Couldn't delete the watch: ${err.message}`),
              })
            }
          >
            <Trash2 />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
