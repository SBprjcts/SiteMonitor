import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider } from "react-router"

import { Toaster } from "@/components/ui/sonner"
import { ApiError } from "@/api/client"
import { TooltipProvider } from "@/components/ui/tooltip"
import { ME_KEY } from "@/hooks/useAuth"
import { router } from "@/routes"
import "./index.css"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 10_000, retry: 1 },
  },
  queryCache: new QueryCache({
    // The session expired (or was ended elsewhere): show the login page.
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) {
        queryClient.setQueryData(ME_KEY, null)
      }
    },
  }),
})

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <RouterProvider router={router} />
        <Toaster theme="dark" />
      </TooltipProvider>
    </QueryClientProvider>
  </StrictMode>,
)
