import { ComingSoon } from "@/components/ComingSoon"
import { PageHeader } from "@/components/layout/PageHeader"

export function ProductDetailPage() {
  return (
    <>
      <PageHeader title="Product" description="Stock by size and event history." />
      <ComingSoon what="Product history" />
    </>
  )
}
