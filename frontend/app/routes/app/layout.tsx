import { useTranslation } from "react-i18next"
import type * as React from "react"
import { Outlet } from "react-router"

import { SidebarInset, SidebarProvider } from "~/components/ui/sidebar"
import { Spinner } from "~/components/ui/spinner"
import { requireUser } from "~/features/auth/lib/require-user"
import { AppSidebar } from "~/features/shell/components/AppSidebar"
import { SiteHeader } from "~/features/shell/components/SiteHeader"

import type { Route } from "./+types/layout"

/** Runs before child loaders on every client navigation into the private area. */
export const clientMiddleware: Route.ClientMiddlewareFunction[] = [
  async ({ request }) => {
    await requireUser(request)
  },
]

export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  return { user: await requireUser(request) }
}

// Also run on hydration, so the first document load of /chat is guarded.
clientLoader.hydrate = true as const

export function HydrateFallback() {
  const { t } = useTranslation("common")
  return (
    <main className="flex min-h-svh items-center justify-center gap-2 text-sm text-muted-foreground">
      <Spinner />
      <span>{t("actions.loading")}</span>
    </main>
  )
}

// The site header of the dashboard-01 block reads its height from this variable; the chat
// page sizes itself as the viewport minus 3rem.
const SHELL_STYLE: React.CSSProperties & { "--header-height": string } = {
  "--header-height": "3rem",
}

export default function AppLayout({ loaderData }: Route.ComponentProps) {
  return (
    <SidebarProvider style={SHELL_STYLE}>
      <AppSidebar user={loaderData.user} />
      <SidebarInset>
        <SiteHeader />
        <Outlet />
      </SidebarInset>
    </SidebarProvider>
  )
}
