import { http, HttpResponse } from "msw"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { AuditEventView } from "~/api/gen/schemas"
import { MyActivity } from "~/features/audit/components/MyActivity"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

function event(id: string, title: string): AuditEventView {
  return {
    id,
    occurred_at: "2026-10-11T09:00:00Z",
    actor_user_id: "u1",
    actor_name: "An",
    actor_was_superadmin: false,
    action: "collection.created",
    organization_id: null,
    subject_user_id: "u1",
    collection_id: "c1",
    details: { title },
  }
}

describe("MyActivity", () => {
  test("lists events as sentences and loads the next page on request", async () => {
    const cursors: (string | null)[] = []
    worker.use(
      http.get("*/api/v1/account/audit", ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor")
        cursors.push(cursor)
        return cursor === null
          ? HttpResponse.json({
              items: [event("e1", "A")],
              next_cursor: "next",
            })
          : HttpResponse.json({ items: [event("e2", "B")], next_cursor: null })
      })
    )
    await render(
      <TestProviders>
        <MyActivity />
      </TestProviders>
    )
    await expect
      .element(page.getByText("An đã tạo bộ tài liệu A"))
      .toBeVisible()
    await page.getByRole("button", { name: "Xem thêm" }).click()
    await expect
      .element(page.getByText("An đã tạo bộ tài liệu B"))
      .toBeVisible()
    await expect
      .element(page.getByRole("button", { name: "Xem thêm" }))
      .not.toBeInTheDocument()
    expect(cursors).toEqual([null, "next"])
  })

  test("says when there is nothing yet", async () => {
    worker.use(
      http.get("*/api/v1/account/audit", () =>
        HttpResponse.json({ items: [], next_cursor: null })
      )
    )
    await render(
      <TestProviders>
        <MyActivity />
      </TestProviders>
    )
    await expect.element(page.getByText("Chưa có hoạt động nào.")).toBeVisible()
  })
})
