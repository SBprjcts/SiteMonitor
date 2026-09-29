import { ComingSoon } from "@/components/ComingSoon"
import { PageHeader } from "@/components/layout/PageHeader"

export function DashboardPage() {
  return (
    <>
      <PageHeader title="Dashboard" description="Live restock feed and store health." />
      <ComingSoon what="The live event feed" />
    </>
  )
}
