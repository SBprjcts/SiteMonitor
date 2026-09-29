import { ComingSoon } from "@/components/ComingSoon"
import { PageHeader } from "@/components/layout/PageHeader"

export function StoresPage() {
  return (
    <>
      <PageHeader title="Stores" description="Shopify stores being monitored." />
      <ComingSoon what="The store list" />
    </>
  )
}
