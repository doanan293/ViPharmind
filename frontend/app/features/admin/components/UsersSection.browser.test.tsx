import { HttpResponse, http } from "msw"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"

import type { AdminUserView } from "~/api/gen/schemas"
import { UsersSection } from "~/features/admin/components/UsersSection"

import { renderWithProviders } from "../../../../tests/chat/render"
import { worker } from "../../../../tests/msw/browser"

const BINH = "99999999-9999-4999-8999-999999999999"
const CHI = "88888888-8888-4888-8888-888888888888"
const HTTP_FORBIDDEN = 403

function user(overrides: Partial<AdminUserView> = {}): AdminUserView {
  return {
    id: BINH,
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

const CHI_USER = user({
  id: CHI,
  display_name: "Chi",
  email: null,
  phone_number: "+84901234567",
  is_superadmin: true,
})

/** Serves Bình, whose fields follow the last PATCH; returns the PATCH bodies. */
function serveBinh(initial: Partial<AdminUserView> = {}): unknown[] {
  const patches: unknown[] = []
  let current = user(initial)
  worker.use(
    http.get("*/api/v1/admin/users", () =>
      HttpResponse.json({ items: [current], next_cursor: null })
    ),
    http.patch(`*/api/v1/admin/users/${BINH}`, async ({ request }) => {
      const body = (await request.json()) as Partial<AdminUserView>
      patches.push(body)
      current = { ...current, ...body }
      return HttpResponse.json(current)
    })
  )
  return patches
}

describe("UsersSection list", () => {
  test("searches by the typed text and loads the next page on request", async () => {
    const requests: { q: string | null; cursor: string | null }[] = []
    worker.use(
      http.get("*/api/v1/admin/users", ({ request }) => {
        const params = new URL(request.url).searchParams
        const q = params.get("q")
        const cursor = params.get("cursor")
        requests.push({ q, cursor })
        if (q !== null) {
          return HttpResponse.json({ items: [CHI_USER], next_cursor: null })
        }
        return cursor === null
          ? HttpResponse.json({ items: [user()], next_cursor: "page-2" })
          : HttpResponse.json({ items: [CHI_USER], next_cursor: null })
      })
    )
    await renderWithProviders(<UsersSection />)
    await expect.element(page.getByText("binh@example.com")).toBeVisible()
    await page.getByRole("button", { name: "Tải thêm" }).click()
    await expect.element(page.getByText("+84901234567")).toBeVisible()
    await expect.element(page.getByText("Quản trị viên")).toBeVisible()
    await expect
      .element(page.getByRole("button", { name: "Tải thêm" }))
      .not.toBeInTheDocument()

    await page
      .getByRole("searchbox", {
        name: "Tìm theo tên, email hoặc số điện thoại",
      })
      .fill("  chi ")
    await expect
      .element(page.getByText("binh@example.com"))
      .not.toBeInTheDocument()
    expect(requests).toContainEqual({ q: "chi", cursor: null })
    expect(requests.slice(0, 2)).toEqual([
      { q: null, cursor: null },
      { q: null, cursor: "page-2" },
    ])
  })

  test("opens a user's conversations from the row", async () => {
    serveBinh()
    worker.use(
      http.get(`*/api/v1/admin/users/${BINH}/conversations`, () =>
        HttpResponse.json({ items: [], next_cursor: null })
      )
    )
    await renderWithProviders(<UsersSection />)
    await page.getByRole("button", { name: "Hội thoại" }).click()
    await expect
      .element(page.getByRole("dialog", { name: "Hội thoại của Bình" }))
      .toBeVisible()
    await expect
      .element(page.getByText("Người dùng chưa có hội thoại nào."))
      .toBeVisible()
  })
})

describe("UsersSection quota", () => {
  test("saves a user's own quota and shows it in the table", async () => {
    const patches = serveBinh()
    await renderWithProviders(<UsersSection />)
    await page.getByRole("button", { name: "Hạn mức" }).click()
    await expect
      .element(page.getByRole("dialog", { name: "Hạn mức của Bình" }))
      .toBeVisible()
    await page.getByLabelText("Số ký tự nội dung").fill("5000")
    await page.getByLabelText("Số bộ tài liệu").fill("3")
    await page.getByRole("button", { name: "Lưu hạn mức" }).click()
    await expect
      .poll(() => patches)
      .toEqual([{ text_quota_bytes: 5000, collection_quota: 3 }])
    await expect.element(page.getByText("Đã lưu hạn mức.")).toBeVisible()
    await expect.element(page.getByText("5.000 ký tự · 3 bộ")).toBeVisible()
    await expect.element(page.getByRole("dialog")).not.toBeInTheDocument()
  })

  test("closing the quota dialog saves nothing", async () => {
    const patches = serveBinh()
    await renderWithProviders(<UsersSection />)
    await page.getByRole("button", { name: "Hạn mức" }).click()
    await page.getByRole("dialog").getByRole("button", { name: "Huỷ" }).click()
    await expect.element(page.getByRole("dialog")).not.toBeInTheDocument()
    expect(patches).toEqual([])
  })
})

describe("UsersSection enable and disable", () => {
  test("enables a disabled user after confirming", async () => {
    const patches = serveBinh({ is_active: false })
    await renderWithProviders(<UsersSection />)
    await page.getByRole("button", { name: "Mở khoá" }).click()
    await expect
      .element(
        page.getByRole("alertdialog", { name: "Mở khoá tài khoản Bình?" })
      )
      .toBeVisible()
    await page.getByRole("button", { name: "Xác nhận" }).click()
    await expect.poll(() => patches).toEqual([{ is_active: true }])
    await expect.element(page.getByText("Đã mở khoá Bình.")).toBeVisible()
    await expect.element(page.getByText("Đang hoạt động")).toBeVisible()
  })

  test("a refused change shows the error, and cancelling closes the confirmation", async () => {
    serveBinh()
    worker.use(
      http.patch(`*/api/v1/admin/users/${BINH}`, () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Forbidden",
            status: HTTP_FORBIDDEN,
            code: "FORBIDDEN_ROLE",
          },
          {
            status: HTTP_FORBIDDEN,
            headers: { "Content-Type": "application/problem+json" },
          }
        )
      )
    )
    await renderWithProviders(<UsersSection />)
    await page.getByRole("button", { name: "Khoá" }).click()
    await page.getByRole("button", { name: "Xác nhận" }).click()
    await expect
      .element(page.getByText("Vai trò của bạn không làm được thao tác này."))
      .toBeVisible()
    const dialog = page.getByRole("alertdialog")
    await dialog.getByRole("button", { name: "Huỷ" }).click()
    await expect.element(dialog).not.toBeInTheDocument()
    await expect.element(page.getByText("Đang hoạt động")).toBeVisible()
  })
})
