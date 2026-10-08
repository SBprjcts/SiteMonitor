import { Navigate, Outlet, useLocation } from "react-router"

import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useMe } from "@/hooks/useAuth"

/** Shows the app only to a logged-in user; everyone else is sent to /login. */
export function RequireAuth() {
  const { data: user, isPending, error, refetch } = useMe()
  const location = useLocation()

  if (isPending) {
    return (
      <div className="flex min-h-svh items-center justify-center bg-background">
        <Skeleton className="h-8 w-40" />
      </div>
    )
  }
  if (error) {
    return (
      <div className="flex min-h-svh flex-col items-center justify-center gap-3 bg-background text-sm text-foreground">
        <p className="text-destructive">Couldn&apos;t reach the server: {error.message}</p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          Try again
        </Button>
      </div>
    )
  }
  if (!user) {
    // Remember where they were going, so login can send them back there.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <Outlet />
}
