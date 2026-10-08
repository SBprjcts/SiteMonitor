import { createBrowserRouter } from "react-router"

import { AppShell } from "@/components/layout/AppShell"
import { RequireAuth } from "@/components/layout/RequireAuth"
import { DashboardPage } from "@/pages/DashboardPage"
import { LoginPage } from "@/pages/LoginPage"
import { NewWatchPage } from "@/pages/NewWatchPage"
import { NotFoundPage } from "@/pages/NotFoundPage"
import { ProductDetailPage } from "@/pages/ProductDetailPage"
import { SettingsPage } from "@/pages/SettingsPage"
import { StoresPage } from "@/pages/StoresPage"
import { WatchesPage } from "@/pages/WatchesPage"

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    // Everything else needs a logged-in user.
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/", element: <DashboardPage /> },
          { path: "/watches", element: <WatchesPage /> },
          { path: "/watches/new", element: <NewWatchPage /> },
          { path: "/products/:id", element: <ProductDetailPage /> },
          { path: "/stores", element: <StoresPage /> },
          { path: "/settings", element: <SettingsPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
])
