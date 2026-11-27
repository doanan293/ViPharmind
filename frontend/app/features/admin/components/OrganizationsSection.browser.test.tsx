import { HttpResponse, http } from "msw"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"

import type { AdminOrganizationView } from "~/api/gen/schemas"
import { OrganizationsSection } from "~/features/admin/components/OrganizationsSection"

import { renderWithProviders } from "../../../../tests/chat/render"
import { worker } from "../../../../tests/msw/browser"

const ORG = "a1a1a1a1-0000-4000-8000-000000000001"

function organization(
  overrides: Partial<AdminOrganizationView> = {}
): AdminOrganizationView {
  return {
    id: ORG,
    name: "Khoa Dược Bạch Mai",
    member_count: 12,
    text_quota_bytes: null,
    collection_quota: null,
    created_at: "2026-10-11T09:00:00Z",
    ...overrides,
  }
}

/** Serves one organization whose quota follows the last PATCH; returns the PATCH bodies. */
function serveOrganization(): unknown[] {
  const patches: unknown[] = []
  let current = organization()
  worker.use(
    http.get("*/api/v1/admin/organizations", () =>
      HttpResponse.json({ items: [current], next_cursor: null })
    ),
    http.patch(`*/api/v1/admin/organizations/${ORG}`, async ({ request }) => {
      const body = (await request.json()) as Partial<AdminOrganizationView>
      patches.push(body)
      current = { ...current, ...body }
      return HttpResponse.json(current)
    })
  )
  return patches
}

describe("OrganizationsSection", () => {
  test("lists organizations with their member count and default quota", async () => {
    serveOrganization()
    await renderWithProviders(<OrganizationsSection />)
    await expect.element(page.getByText("Khoa Dược Bạch Mai")).toBeVisible()
    await expect.element(page.getByText("12", { exact: true })).toBeVisible()
    await expect
      .element(page.getByRole("cell", { name: "Mặc định" }))
      .toBeVisible()
  })

  test("saves an organization's own quota and shows it in the table", async () => {
    const patches = serveOrganization()
    await renderWithProviders(<OrganizationsSection />)
    await page.getByRole("button", { name: "Hạn mức" }).click()
    await expect
      .element(
        page.getByRole("dialog", { name: "Hạn mức của Khoa Dược Bạch Mai" })
      )
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
})

describe("OrganizationsSection quota dialog", () => {
  test("rejects a negative quota without calling the API", async () => {
    const patches = serveOrganization()
    await renderWithProviders(<OrganizationsSection />)
    await page.getByRole("button", { name: "Hạn mức" }).click()
    await page.getByLabelText("Số bộ tài liệu").fill("-1")
    await page.getByRole("button", { name: "Lưu hạn mức" }).click()
    await expect
      .element(page.getByLabelText("Số bộ tài liệu"))
      .toHaveAttribute("aria-invalid", "true")
    expect(patches).toEqual([])
  })

  test("shows the server's error and keeps the dialog open when saving fails", async () => {
    serveOrganization()
    worker.use(
      http.patch(`*/api/v1/admin/organizations/${ORG}`, () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Forbidden",
            status: 403,
            code: "forbidden",
          },
          {
            status: 403,
            headers: { "Content-Type": "application/problem+json" },
          }
        )
      )
    )
    await renderWithProviders(<OrganizationsSection />)
    await page.getByRole("button", { name: "Hạn mức" }).click()
    await page.getByLabelText("Số bộ tài liệu").fill("2")
    await page.getByRole("button", { name: "Lưu hạn mức" }).click()
    await expect.element(page.getByRole("dialog")).toBeVisible()
    await expect
      .element(page.getByRole("dialog").getByRole("alert"))
      .toBeVisible()
  })
})

describe("OrganizationsSection dialog and paging", () => {
  test("cancel closes the dialog without saving", async () => {
    const patches = serveOrganization()
    await renderWithProviders(<OrganizationsSection />)
    await page.getByRole("button", { name: "Hạn mức" }).click()
    await page.getByRole("button", { name: "Huỷ" }).click()
    await expect.element(page.getByRole("dialog")).not.toBeInTheDocument()
    expect(patches).toEqual([])
  })

  test("loads the next page on demand", async () => {
    worker.use(
      http.get("*/api/v1/admin/organizations", ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor")
        return cursor === null
          ? HttpResponse.json({ items: [organization()], next_cursor: "p2" })
          : HttpResponse.json({
              items: [
                organization({
                  id: "a1a1a1a1-0000-4000-8000-000000000002",
                  name: "Bệnh viện Nhi",
                }),
              ],
              next_cursor: null,
            })
      })
    )
    await renderWithProviders(<OrganizationsSection />)
    await page.getByRole("button", { name: "Tải thêm" }).click()
    await expect.element(page.getByText("Bệnh viện Nhi")).toBeVisible()
    await expect
      .element(page.getByRole("button", { name: "Tải thêm" }))
      .not.toBeInTheDocument()
  })
})
