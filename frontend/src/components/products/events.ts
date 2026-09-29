import { ArrowDownRight, PackageCheck, PackageX, Sparkles, type LucideIcon } from "lucide-react"

import type { EventType } from "@/api/types"

export const EVENT_META: Record<EventType, { label: string; icon: LucideIcon; color: string }> = {
  restock: { label: "Restock", icon: PackageCheck, color: "text-emerald-500" },
  sold_out: { label: "Sold out", icon: PackageX, color: "text-red-500" },
  price_drop: { label: "Price drop", icon: ArrowDownRight, color: "text-sky-500" },
  new_product: { label: "New product", icon: Sparkles, color: "text-violet-500" },
}
