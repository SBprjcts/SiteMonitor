import { ExternalLink } from "lucide-react"
import { toast } from "sonner"

import type { Store } from "@/api/types"
import { PageHeader } from "@/components/layout/PageHeader"
import { AddStoreDialog } from "@/components/stores/AddStoreDialog"
import { StoreStatusBadge } from "@/components/stores/StoreStatusBadge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useMe } from "@/hooks/useAuth"
import { useStores, useToggleStore } from "@/hooks/useStores"
import { formatRelativeTime } from "@/lib/format"

export function StoresPage() {
  const { data: stores, isPending, error, refetch } = useStores()

  const active = stores?.filter((s) => s.enabled).length ?? 0

  return (
    <>
      <PageHeader
        title="Stores"
        description={
          stores
            ? `${active} of ${stores.length} stores are being monitored.`
            : "Shopify stores being monitored."
        }
        actions={<AddStoreDialog />}
      />

      {error ? (
        <Card className="flex flex-col items-center gap-3 py-10 text-sm">
          <p className="text-destructive">Couldn&apos;t load stores: {error.message}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Try again
          </Button>
        </Card>
      ) : (
        <Card className="py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Store</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden sm:table-cell">Last checked</TableHead>
                <TableHead className="pr-4 text-right">Monitor</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isPending
                ? Array.from({ length: 6 }, (_, i) => <SkeletonRow key={i} />)
                : stores.map((store) => <StoreRow key={store.id} store={store} />)}
            </TableBody>
          </Table>
        </Card>
      )}
    </>
  )
}

function StoreRow({ store }: { store: Store }) {
  const toggle = useToggleStore()
  // Stores are shared by every user, so only admins can turn one on or off.
  const isAdmin = useMe().data?.is_admin ?? false
  const unsupported = store.platform === "shopify_hydrogen"

  function onToggle(enabled: boolean) {
    toggle.mutate(
      { id: store.id, enabled },
      { onError: (err) => toast.error(`Couldn't update ${store.name}: ${err.message}`) },
    )
  }

  const monitorSwitch = (
    <Switch
      checked={store.enabled}
      onCheckedChange={onToggle}
      disabled={unsupported}
      aria-label={`Monitor ${store.name}`}
    />
  )

  return (
    <TableRow>
      <TableCell className="pl-4">
        <div className="font-medium">{store.name}</div>
        <a
          href={`https://${store.domain}`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          {store.domain}
          <ExternalLink className="size-3" />
        </a>
      </TableCell>
      <TableCell>
        <StoreStatusBadge store={store} />
        {store.status !== "ok" && store.consecutive_errors > 0 && (
          <div className="mt-1 text-xs text-muted-foreground">
            {store.consecutive_errors} failed checks in a row
          </div>
        )}
      </TableCell>
      <TableCell className="hidden text-sm text-muted-foreground sm:table-cell">
        {store.last_ok_at ? formatRelativeTime(store.last_ok_at) : "Never"}
      </TableCell>
      <TableCell className="pr-4 text-right">
        {!isAdmin ? (
          <span className="text-sm text-muted-foreground">{store.enabled ? "On" : "Paused"}</span>
        ) : unsupported ? (
          <Tooltip>
            <TooltipTrigger asChild>
              {/* span keeps the tooltip working on a disabled switch */}
              <span className="inline-flex">{monitorSwitch}</span>
            </TooltipTrigger>
            <TooltipContent>Headless Shopify store: needs the Hydrogen adapter</TooltipContent>
          </Tooltip>
        ) : (
          monitorSwitch
        )}
      </TableCell>
    </TableRow>
  )
}

function SkeletonRow() {
  return (
    <TableRow>
      <TableCell className="pl-4">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-1.5 h-3 w-24" />
      </TableCell>
      <TableCell>
        <Skeleton className="h-5 w-20" />
      </TableCell>
      <TableCell className="hidden sm:table-cell">
        <Skeleton className="h-4 w-24" />
      </TableCell>
      <TableCell className="pr-4">
        <Skeleton className="ml-auto h-5 w-8" />
      </TableCell>
    </TableRow>
  )
}
