import { ComingSoon } from "@/components/ComingSoon"
import { PageHeader } from "@/components/layout/PageHeader"

export function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Discord webhooks and account settings." />
      <ComingSoon what="Webhook management" />
    </>
  )
}
