import { Footprints } from "lucide-react"

import { cn } from "@/lib/utils"

export function ProductThumb({ src, className }: { src: string | null; className?: string }) {
  return (
    <div
      className={cn(
        "flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted",
        className,
      )}
    >
      {src ? (
        <img src={src} alt="" className="size-full object-cover" loading="lazy" />
      ) : (
        <Footprints className="size-1/2 text-muted-foreground" />
      )}
    </div>
  )
}
