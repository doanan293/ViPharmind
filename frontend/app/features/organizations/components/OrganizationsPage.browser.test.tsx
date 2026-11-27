import { HttpResponse, http } from "msw"
import { createRoutesStub, useParams } from "react-router"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { OrganizationView } from "~/api/gen/schemas"
import { OrganizationsPage } from "~/features/organizations/components/OrganizationsPage"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const ORG = "11111111-1111-4111-8111-111111111111"
const CREATED = "77777777-7777-4777-8777-777777777777"

function organization(
  overrides: Partial<OrganizationView> = {}
): OrganizationView {
  return {
    id: ORG,
    name: "Khoa Dược",
    role: "editor",
    member_count: 3,
    created_at: "2026-10-11T09:00:00Z",
    ...overrides,
  }
}

/** The organization page a link or a created organization opens. */
function OrganizationStub() {
  const { organizationId } = useParams()
  return <p>Tổ chức {organizationId}</p>
}

async function open(organizations: OrganizationView[]) {
  worker.use(
    http.get("*/api/v1/organizations", () => HttpResponse.json(organizations))
  )
  const Stub = createRoutesStub([
    { path: "/organizations", Component: OrganizationsPage },
    { path: "/organizations/:organizationId", Component: OrganizationStub },
  ])
  await render(
    <TestProviders>
      <Stub initialEntries={["/organizations"]} />
    </TestProviders>
  )
}

describe("OrganizationsPage", () => {
  test("lists the user's organizations with member count and role, linking to each", async () => {
    await open([
      organization(),
      organization({
        id: "88888888-8888-4888-8888-888888888888",
        name: "Bệnh viện Nhi",
        role: null,
        member_count: 1,
      }),
    ])
    await expect.element(page.getByText("3 thành viên")).toBeVisible()
    await expect.element(page.getByText("Biên tập viên")).toBeVisible()
    // A superadmin who is not a member sees the organization with the admin badge.
    await expect.element(page.getByText("Quản trị viên")).toBeVisible()
    await page.getByRole("link", { name: /Khoa Dược/ }).click()
    await expect.element(page.getByText(`Tổ chức ${ORG}`)).toBeVisible()
  })

  test("says so when the user belongs to no organization", async () => {
    await open([])
    await expect
      .element(page.getByText("Bạn chưa thuộc tổ chức nào."))
      .toBeVisible()
  })

  test("a blank name is rejected and nothing is created", async () => {
    let created = 0
    worker.use(
      http.post("*/api/v1/organizations", () => {
        created += 1
        return HttpResponse.json(organization())
      })
    )
    await open([])
    await page.getByLabelText("Tên tổ chức").fill("   ")
    await page.getByRole("button", { name: "Tạo", exact: true }).click()
    await expect.element(page.getByText("Nhập tên tổ chức.")).toBeVisible()
    expect(created).toBe(0)
  })
})

describe("OrganizationsPage creation", () => {
  test("creating an organization opens it", async () => {
    const created: unknown[] = []
    worker.use(
      http.post("*/api/v1/organizations", async ({ request }) => {
        created.push(await request.json())
        return HttpResponse.json(
          organization({ id: CREATED, name: "Khoa Nội", role: "owner" }),
          { status: 201 }
        )
      })
    )
    await open([])
    await page.getByLabelText("Tên tổ chức").fill("  Khoa Nội ")
    await page.getByRole("button", { name: "Tạo", exact: true }).click()
    await expect.poll(() => created).toEqual([{ name: "Khoa Nội" }])
    await expect.element(page.getByText(`Tổ chức ${CREATED}`)).toBeVisible()
  })

  test("a server error that is not about the name shows under the form", async () => {
    worker.use(
      http.post("*/api/v1/organizations", () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Too many",
            status: 429,
            code: "RATE_LIMITED",
          },
          {
            status: 429,
            headers: { "Content-Type": "application/problem+json" },
          }
        )
      )
    )
    await open([])
    await page.getByLabelText("Tên tổ chức").fill("Khoa Nội")
    await page.getByRole("button", { name: "Tạo", exact: true }).click()
    await expect
      .element(page.getByText("Bạn thao tác quá nhanh. Vui lòng thử lại sau."))
      .toBeVisible()
  })
})
