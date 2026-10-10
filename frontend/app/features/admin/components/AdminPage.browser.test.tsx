import { http, HttpResponse } from "msw"
import { createRoutesStub } from "react-router"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { AdminUserView } from "~/api/gen/schemas"
import { queryClient } from "~/api/query-client"
import { Toaster } from "~/components/ui/toast"
import { AdminPage } from "~/features/admin/components/AdminPage"
import { adminLoader } from "~/features/admin/lib/require-superadmin"

import { worker } from "../../../../tests/msw/browser"
import { accountView } from "../../../../tests/utils/account"
import { TestProviders } from "../../../../tests/utils/providers"

const USER = "99999999-9999-4999-8999-999999999999"

function user(overrides: Partial<AdminUserView> = {}): AdminUserView {
  return {
    id: USER,
    display_name: "Bình",
    email: "binh@example.com",
    phone_number: null,
    is_active: true,
    is_superadmin: false,
    text_quota_bytes: null,
    collection_quota: null,
    created_at: "2026-10-11T09:00:00Z",
    ...overrides,
  }
}

async function open(superadmin: boolean, collections: unknown[] = []) {
  queryClient.clear()
  worker.use(
    http.get("*/api/v1/users/me", () =>
      HttpResponse.json(accountView({ is_superadmin: superadmin }))
    ),
    // The overview cards of the dashboard.
    http.get("*/api/v1/admin/collections", () =>
      HttpResponse.json(collections)
    ),
    http.get("*/api/v1/admin/ingest-jobs", () => HttpResponse.json([]))
  )
  const Stub = createRoutesStub([
    {
      path: "/admin/:section?",
      loader: adminLoader,
      Component: () => <AdminPage section="users" />,
      ErrorBoundary: () => <p>Không tìm thấy trang</p>,
      HydrateFallback: () => <p>Đang tải</p>,
    },
  ])
  await render(
    <TestProviders>
      <Toaster>
        <Stub initialEntries={["/admin"]} />
      </Toaster>
    </TestProviders>
  )
}

describe("AdminPage", () => {
  test("is a 404 for anyone who is not a superadmin", async () => {
    await open(false)
    await expect.element(page.getByText("Không tìm thấy trang")).toBeVisible()
    await expect
      .element(page.getByRole("tab", { name: "Người dùng" }))
      .not.toBeInTheDocument()
  })

  test("a superadmin disables a user after confirming", async () => {
    const patches: unknown[] = []
    let active = true
    worker.use(
      http.get("*/api/v1/admin/users", () =>
        HttpResponse.json({
          items: [user({ is_active: active })],
          next_cursor: null,
        })
      ),
      http.patch(`*/api/v1/admin/users/${USER}`, async ({ request }) => {
        patches.push(await request.json())
        active = false
        return HttpResponse.json(user({ is_active: false }))
      })
    )
    await open(true)
    await expect.element(page.getByText("binh@example.com")).toBeVisible()
    await page.getByRole("button", { name: "Khoá" }).click()
    await page.getByRole("button", { name: "Xác nhận" }).click()
    await expect.poll(() => patches).toEqual([{ is_active: false }])
    await expect
      .element(page.getByText("Đã khoá", { exact: true }))
      .toBeVisible()
  })

  test("the overview cards add up the collections", async () => {
    const stat = (id: string, documents: number, points: number) => ({
      collection: {
        id,
        key: id,
        title: id,
        visibility: "private",
        owner_user_id: null,
        owner_organization_id: null,
        owner_name: "",
        is_system: false,
        can_edit: false,
        can_set_public: false,
        current_release_id: null,
        current_release_number: id === "a" ? 1 : null,
      },
      documents,
      qdrant_points: points,
    })
    worker.use(
      http.get("*/api/v1/admin/users", () =>
        HttpResponse.json({ items: [], next_cursor: null })
      )
    )
    await open(true, [stat("a", 3, 1200), stat("b", 4, 800)])
    await expect.element(page.getByText("2.000")).toBeVisible()
    await expect
      .element(page.getByText("1 đang có bản phát hành"))
      .toBeVisible()
    await expect.element(page.getByText("7", { exact: true })).toBeVisible()
  })
})
