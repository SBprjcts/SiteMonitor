import type { Variant } from "@/api/types"
import { cn } from "@/lib/utils"

interface SizeGridProps {
  variants: Variant[]
  /** Selected variant external ids. Omit for a read-only grid. */
  selected?: Set<string>
  onToggle?: (externalId: string) => void
  /** Read-only grids can link each in-stock size somewhere (e.g. its cart link). */
  hrefFor?: (variant: Variant) => string | undefined
}

/** A grid of size chips showing stock; optionally selectable. */
export function SizeGrid({ variants, selected, onToggle, hrefFor }: SizeGridProps) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(4.5rem,1fr))] gap-2">
      {variants.map((variant) => {
        const isSelected = selected?.has(variant.external_id) ?? false
        const className = cn(
          "flex flex-col items-center justify-center rounded-md border px-2 py-2 text-sm transition-colors",
          variant.available
            ? "border-border bg-card"
            : "border-dashed border-border/70 bg-transparent text-muted-foreground",
          isSelected && "border-primary bg-primary text-primary-foreground",
          (onToggle || hrefFor) && "hover:border-foreground/40",
        )
        const content = (
          <>
            <span className={cn("font-medium", !variant.available && !isSelected && "line-through")}>
              {variant.size}
            </span>
            <span className={cn("text-[11px]", isSelected ? "opacity-80" : "text-muted-foreground")}>
              {variant.available ? "In stock" : "Sold out"}
            </span>
          </>
        )

        if (onToggle) {
          return (
            <button
              key={variant.id}
              type="button"
              aria-pressed={isSelected}
              onClick={() => onToggle(variant.external_id)}
              className={className}
            >
              {content}
            </button>
          )
        }
        const href = variant.available ? hrefFor?.(variant) : undefined
        return href ? (
          <a key={variant.id} href={href} target="_blank" rel="noreferrer" className={className}>
            {content}
          </a>
        ) : (
          <div key={variant.id} className={className}>
            {content}
          </div>
        )
      })}
    </div>
  )
}
