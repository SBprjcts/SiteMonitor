import type { Store } from "@/api/types"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

const STYLES: Record<Store["status"], { label: string; dot: string }> = {
  ok: { label: "Healthy", dot: "bg-emerald-500" },
  degraded: { label: "Degraded", dot: "bg-amber-500" },
  blocked: { label: "Blocked", dot: "bg-red-500" },
}

export function StoreStatusBadge({ store }: { store: Store }) {
  if (store.platform === "shopify_hydrogen") {
    return <Badge variant="outline">Not supported yet</Badge>
  }
  if (!store.enabled) {
    return <Badge variant="secondary">Paused</Badge>
  }
  // "Healthy" would be misleading before the monitor has checked the store at all.
  if (store.last_ok_at === null && store.consecutive_errors === 0) {
    return <Badge variant="outline">Not checked yet</Badge>
  }
  const { label, dot } = STYLES[store.status]
  return (
    <Badge variant="outline">
      <span className={cn("size-1.5 rounded-full", dot)} aria-hidden />
      {label}
    </Badge>
  )
}
