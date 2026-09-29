import { ComingSoon } from "@/components/ComingSoon"
import { PageHeader } from "@/components/layout/PageHeader"

export function NewWatchPage() {
  return (
    <>
      <PageHeader title="New watch" description="Watch a product, a style code, or a keyword set." />
      <ComingSoon what="Adding watches" />
    </>
  )
}
