import { HttpResponse, http } from "msw"
import { createRoutesStub, useParams } from "react-router"
import { afterEach, describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { AdminUserView } from "~/api/gen/schemas"
import { queryClient } from "~/api/query-client"
import { Toaster } from "~/components/ui/toast"
import { AdminPage } from "~/features/admin/components/AdminPage"
import { adminLoader } from "~/features/admin/lib/require-superadmin"

import { worker } from "../../../../tests/msw/browser"
import { accountView } from "../../../../tests/utils/account"
import {
  createTestQueryClient,
  TestProviders,
} from "../../../../tests/utils/providers"

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

/** Passes the URL's section, as the route module does, so switching tabs navigates. */
function AdminRoute() {
  const { section } = useParams()
  return <AdminPage section={section} />
}

function NotFound() {
  return <p>Không tìm thấy trang</p>
}

function Loading() {
  return <p>Đang tải</p>
}

const Stub = createRoutesStub([
  {
    path: "/admin/:section?",
    loader: adminLoader,
    Component: AdminRoute,
    ErrorBoundary: NotFound,
    HydrateFallback: Loading,
  },
])

/** The query client of the rendered page. */
let client = createTestQueryClient()

// Wait until every request has been answered while the test's handlers are still installed;
// one landing after the reset fails as unhandled.
afterEach(async () => {
  await expect.poll(() => client.isFetching() + client.isMutating()).toBe(0)
})

async function open(
  superadmin: boolean,
  collections: unknown[] = [],
  section = "users",
  jobs: unknown[] = []
) {
  queryClient.clear()
  client = createTestQueryClient()
  worker.use(
    http.get("*/api/v1/users/me", () =>
      HttpResponse.json(accountView({ is_superadmin: superadmin }))
    ),
    // The overview cards of the dashboard.
    http.get("*/api/v1/admin/collections", () =>
      HttpResponse.json(collections)
    ),
    http.get("*/api/v1/admin/ingest-jobs", () => HttpResponse.json(jobs))
  )
  await render(
    <TestProviders client={client}>
      <Toaster>
        <Stub initialEntries={[`/admin/${section}`]} />
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
})

/** A collection row of the overview with its document and vector counts; only "a" is released. */
function stat(
  id: string,
  { documents, points }: { documents: number; points: number }
) {
  return {
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
  }
}

describe("AdminPage overview", () => {
  test("the overview cards add up the collections", async () => {
    worker.use(
      http.get("*/api/v1/admin/users", () =>
        HttpResponse.json({ items: [], next_cursor: null })
      )
    )
    await open(true, [
      stat("a", { documents: 3, points: 1200 }),
      stat("b", { documents: 4, points: 800 }),
    ])
    await expect.element(page.getByText("2.000")).toBeVisible()
    await expect
      .element(page.getByText("1 đang có bản phát hành"))
      .toBeVisible()
    await expect.element(page.getByText("7", { exact: true })).toBeVisible()
  })

  test("publish jobs name their collection", async () => {
    const id = "c0c0c0c0-0000-4000-8000-000000000001"
    const stat = {
      collection: {
        id,
        key: "phac-do",
        title: "Phác đồ khoa Dược",
        visibility: "organization",
        owner_user_id: null,
        owner_organization_id: null,
        owner_name: "",
        is_system: false,
        can_edit: false,
        can_set_public: false,
        current_release_id: null,
        current_release_number: 1,
      },
      documents: 1,
      qdrant_points: 3,
    }
    const job = {
      id: "j0j0j0j0-0000-4000-8000-000000000001",
      collection_id: id,
      status: "succeeded",
      step: "publish",
      progress: 100,
      error: null,
      attempts: 1,
      release_number: 1,
      created_at: "2026-11-26T05:00:00Z",
      started_at: "2026-11-26T05:00:01Z",
      finished_at: "2026-11-26T05:00:09Z",
    }
    await open(true, [stat], "jobs", [job])
    await expect
      .element(page.getByRole("link", { name: "Phác đồ khoa Dược" }))
      .toBeVisible()
  })
})

describe("AdminPage log", () => {
  test("switching to the log tab lists every audit event", async () => {
    worker.use(
      http.get("*/api/v1/admin/users", () =>
        HttpResponse.json({ items: [user()], next_cursor: null })
      ),
      http.get("*/api/v1/admin/audit", () =>
        HttpResponse.json({
          items: [
            {
              id: "e1",
              occurred_at: "2026-10-11T09:00:00Z",
              actor_user_id: USER,
              actor_name: "Bình",
              actor_was_superadmin: false,
              action: "member.left",
              organization_id: null,
              subject_user_id: USER,
              subject_name: "Bình",
              collection_id: null,
              details: {},
            },
          ],
          next_cursor: null,
        })
      )
    )
    await open(true)
    await expect.element(page.getByText("binh@example.com")).toBeVisible()
    await page.getByRole("tab", { name: "Nhật ký" }).click()
    await expect.element(page.getByText("Bình đã rời tổ chức")).toBeVisible()
    await expect
      .element(page.getByRole("tab", { name: "Nhật ký" }))
      .toHaveAttribute("aria-selected", "true")
  })
})
