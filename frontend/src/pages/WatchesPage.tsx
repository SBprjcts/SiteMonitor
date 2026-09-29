import { ComingSoon } from "@/components/ComingSoon"
import { PageHeader } from "@/components/layout/PageHeader"

export function WatchesPage() {
  return (
    <>
      <PageHeader title="Watches" description="Products, style codes and keywords you are watching." />
      <ComingSoon what="The watch list" />
    </>
  )
}
