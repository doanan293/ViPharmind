import Cookies from "js-cookie"
import { afterEach, beforeEach, expect, test, vi } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { SidebarProvider, SidebarTrigger } from "~/components/ui/sidebar"

/** The cookie the sidebar writes; server rendering reads it to restore the state. */
const SIDEBAR_COOKIE = "sidebar_state"
/** A desktop window: on mobile the sidebar is a sheet and keeps no cookie. */
const DESKTOP = { width: 1280, height: 800 }

beforeEach(async () => {
  await page.viewport(DESKTOP.width, DESKTOP.height)
})

afterEach(() => {
  vi.unstubAllGlobals()
  Cookies.remove(SIDEBAR_COOKIE, { path: "/" })
})

test("toggling the sidebar remembers its state in a cookie", async () => {
  const screen = await render(
    <SidebarProvider>
      <SidebarTrigger />
    </SidebarProvider>
  )

  await screen.getByRole("button", { name: /sidebar/i }).click()

  await expect.poll(() => Cookies.get(SIDEBAR_COOKIE)).toBe("false")
})

test("the state is remembered in browsers without the Cookie Store API", async () => {
  // Firefox and plain-HTTP pages have no window.cookieStore.
  vi.stubGlobal("cookieStore", undefined)
  Reflect.deleteProperty(window, "cookieStore")
  const screen = await render(
    <SidebarProvider>
      <SidebarTrigger />
    </SidebarProvider>
  )

  await screen.getByRole("button", { name: /sidebar/i }).click()

  await expect.poll(() => Cookies.get(SIDEBAR_COOKIE)).toBe("false")
})
