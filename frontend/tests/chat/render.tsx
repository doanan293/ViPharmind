import type { QueryClient } from "@tanstack/react-query"
import { http, HttpResponse } from "msw"
import type { ComponentType, ReactNode } from "react"
import { createRoutesStub, useLocation } from "react-router"
import { render, type RenderResult } from "vitest-browser-react"

import { Toaster } from "~/components/ui/toast"

import { worker } from "../msw/browser"
import { createTestQueryClient, TestProviders } from "../utils/providers"

export type RenderRoutesOptions = {
  initialEntry: string | { pathname: string; state: unknown }
  path?: string
  wrap?: ComponentType<{ children: ReactNode }>
}

export type RenderRoutesResult = {
  screen: RenderResult
  queryClient: QueryClient
}

export function LocationProbe() {
  const location = useLocation()
  return (
    <output data-testid="location">{`${location.pathname}${location.search}`}</output>
  )
}

/**
 * The composer's sources picker reads the conversation's scope. Chat page tests serve
 * "everything visible" unless they register their own handler afterwards.
 */
function serveSourceScope(): void {
  worker.use(
    http.get("*/api/v1/conversations/:conversationId", ({ params }) =>
      HttpResponse.json({
        id: String(params["conversationId"]),
        title: "",
        turn_count: 0,
        created_at: "2026-10-11T09:00:00Z",
        updated_at: "2026-10-11T09:00:00Z",
        collection_ids: null,
      })
    )
  )
}

function PassThrough({ children }: { children: ReactNode }) {
  return <>{children}</>
}

export function renderWithProviders(ui: ReactNode): Promise<RenderResult> {
  return render(
    <TestProviders>
      <Toaster>{ui}</Toaster>
    </TestProviders>
  )
}

export async function renderRoutes(
  Page: ComponentType,
  {
    initialEntry,
    path = "/chat/:conversationId?",
    wrap: Wrap = PassThrough,
  }: RenderRoutesOptions
): Promise<RenderRoutesResult> {
  const queryClient = createTestQueryClient()
  serveSourceScope()

  function RoutePage() {
    return (
      <Wrap>
        <Page />
        <LocationProbe />
      </Wrap>
    )
  }

  const Stub = createRoutesStub([
    { path, Component: RoutePage },
    { path: "/login", Component: LocationProbe },
  ])

  const screen = await render(
    <TestProviders client={queryClient}>
      <Toaster>
        <Stub initialEntries={[initialEntry]} />
      </Toaster>
    </TestProviders>
  )
  return { screen, queryClient }
}
