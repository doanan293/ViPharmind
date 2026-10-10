import { http, HttpResponse } from "msw"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { SessionsList } from "~/features/settings/components/SessionsList"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const SESSIONS = [
  {
    id: "a".repeat(32),
    created_at: "2026-10-10T09:00:00Z",
    last_used_at: "2026-10-10T10:00:00Z",
    user_agent: "Mozilla/5.0 (Windows NT 10.0) Firefox/140.0",
    ip_address: "10.0.0.1",
    current: true,
  },
  {
    id: "b".repeat(32),
    created_at: "2026-10-09T09:00:00Z",
    last_used_at: null,
    user_agent: "Mozilla/5.0 (iPhone) Safari/17.0",
    ip_address: "10.0.0.2",
    current: false,
  },
]

describe("SessionsList", () => {
  test("marks this device and signs out another one", async () => {
    const deleted: string[] = []
    worker.use(
      http.get("/api/v1/account/sessions", () => HttpResponse.json(SESSIONS)),
      http.delete("/api/v1/account/sessions/:id", ({ params }) => {
        deleted.push(String(params.id))
        return new HttpResponse(null, { status: 204 })
      })
    )
    await render(
      <TestProviders>
        <SessionsList />
      </TestProviders>
    )
    await expect.element(page.getByText("Thiết bị này")).toBeVisible()
    await page
      .getByRole("button", { name: "Đăng xuất phiên trên Safari" })
      .click()
    await expect.poll(() => deleted).toEqual(["b".repeat(32)])
  })

  test("says so when the sessions cannot be loaded, and retries", async () => {
    // A flag, not a call count: a refetch left over from the previous test may land here.
    let failing = true
    worker.use(
      http.get("/api/v1/account/sessions", () => {
        return failing
          ? HttpResponse.json(
              { code: "INTERNAL_ERROR", title: "Internal Server Error" },
              {
                status: 500,
                headers: { "Content-Type": "application/problem+json" },
              }
            )
          : HttpResponse.json(SESSIONS)
      })
    )
    await render(
      <TestProviders>
        <SessionsList />
      </TestProviders>
    )
    await expect
      .element(page.getByRole("alert"))
      .toHaveTextContent("Không tải được danh sách phiên đăng nhập.")
    failing = false
    await page.getByRole("button", { name: "Thử lại" }).click()
    await expect.element(page.getByText("Thiết bị này")).toBeVisible()
  })
})
