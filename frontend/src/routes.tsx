import { createBrowserRouter } from "react-router"

import { AppShell } from "@/components/layout/AppShell"
import { DashboardPage } from "@/pages/DashboardPage"
import { NewWatchPage } from "@/pages/NewWatchPage"
import { NotFoundPage } from "@/pages/NotFoundPage"
import { ProductDetailPage } from "@/pages/ProductDetailPage"
import { SettingsPage } from "@/pages/SettingsPage"
import { StoresPage } from "@/pages/StoresPage"
import { WatchesPage } from "@/pages/WatchesPage"

export const router = createBrowserRouter([
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
])
