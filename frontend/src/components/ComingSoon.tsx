import { Card, CardContent } from "@/components/ui/card"

export function ComingSoon({ what }: { what: string }) {
  return (
    <Card>
      <CardContent className="py-10 text-center text-sm text-muted-foreground">
        {what} is coming soon.
      </CardContent>
    </Card>
  )
}
