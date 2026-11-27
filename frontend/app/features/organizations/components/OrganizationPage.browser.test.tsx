import { HttpResponse, http } from "msw"
import { createRoutesStub, useParams } from "react-router"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { InvitationView, OrganizationView } from "~/api/gen/schemas"
import { Toaster } from "~/components/ui/toast"
import { OrganizationPage } from "~/features/organizations/components/OrganizationPage"

import { worker } from "../../../../tests/msw/browser"
import { accountView } from "../../../../tests/utils/account"
import { TestProviders } from "../../../../tests/utils/providers"

const ORG = "11111111-1111-4111-8111-111111111111"
const ME = accountView()
const OTHER = "22222222-2222-4222-8222-222222222222"

function organization(role: OrganizationView["role"]): OrganizationView {
  return {
    id: ORG,
    name: "Khoa Dược",
    role,
    member_count: 2,
    created_at: "2026-10-11T09:00:00Z",
  }
}

function invitation(overrides: Partial<InvitationView> = {}): InvitationView {
  return {
    id: "33333333-3333-4333-8333-333333333333",
    organization_id: ORG,
    email: "x@example.com",
    role: "member",
    status: "pending_approval",
    invited_by: OTHER,
    invited_by_name: "Bình",
    created_at: "2026-10-11T09:00:00Z",
    expires_at: null,
    ...overrides,
  }
}

const served = { members: 0, invitations: 0 }

function serve(
  role: OrganizationView["role"],
  invitations: InvitationView[] = []
) {
  served.members = 0
  served.invitations = 0
  worker.use(
    http.get("*/api/v1/users/me", () => HttpResponse.json(ME)),
    http.get(`*/api/v1/organizations/${ORG}`, () =>
      HttpResponse.json(organization(role))
    ),
    http.get(`*/api/v1/organizations/${ORG}/members`, () => {
      served.members += 1
      return HttpResponse.json([
        {
          user_id: ME.id,
          display_name: "An",
          email: ME.email,
          role,
          joined_at: "2026-10-11T09:00:00Z",
        },
        {
          user_id: OTHER,
          display_name: "Bình",
          email: "b@example.com",
          role: "member",
          joined_at: "2026-10-11T10:00:00Z",
        },
      ])
    }),
    http.get(`*/api/v1/organizations/${ORG}/invitations`, () => {
      served.invitations += 1
      return HttpResponse.json(invitations)
    }),
    http.get("*/api/v1/collections", () =>
      HttpResponse.json({ public: [], organizations: [], mine: [], others: [] })
    )
  )
}

/** Passes the URL's tab, as the route module does, so switching tabs navigates. */
function OrganizationRoute() {
  const { tab } = useParams()
  return <OrganizationPage organizationId={ORG} tab={tab} />
}

function OrganizationsList() {
  return <p>Danh sách tổ chức</p>
}

const Stub = createRoutesStub([
  {
    path: "/organizations/:organizationId/:tab?",
    Component: OrganizationRoute,
  },
  { path: "/organizations", Component: OrganizationsList },
])

async function open(tab = "members") {
  await render(
    <TestProviders>
      <Toaster>
        <Stub initialEntries={[`/organizations/${ORG}/${tab}`]} />
      </Toaster>
    </TestProviders>
  )
}

// Creating or approving an invitation invalidates the list. Wait for that refetch to be answered
// while the test's handlers are still installed; otherwise it lands after the reset (or in the
// next test) as an unhandled request, which fail-on-console turns into a failure.
async function expectInvitationsReloaded() {
  await expect.poll(() => served.invitations).toBe(2)
}

describe("OrganizationPage members", () => {
  test("members see no log tab and no owner actions", async () => {
    serve("member")
    await open()
    await expect
      .element(page.getByRole("heading", { name: "Khoa Dược" }))
      .toBeVisible()
    await expect
      .element(page.getByRole("tab", { name: "Lời mời" }))
      .toBeVisible()
    await expect
      .element(page.getByRole("tab", { name: "Nhật ký" }))
      .not.toBeInTheDocument()
    await expect
      .element(page.getByRole("button", { name: "Đổi tên" }))
      .not.toBeInTheDocument()
    await expect
      .element(page.getByRole("button", { name: "Rời tổ chức" }))
      .toBeVisible()
    // Wait for the member list so its request does not outlive the test.
    await expect.element(page.getByText("Bình")).toBeVisible()
  })

  test("owners change a member's role", async () => {
    serve("owner")
    const bodies: unknown[] = []
    let loadsBeforeChange = 0
    worker.use(
      http.patch(
        `*/api/v1/organizations/${ORG}/members/${OTHER}`,
        async ({ request }) => {
          loadsBeforeChange = served.members
          bodies.push(await request.json())
          return new HttpResponse(null, { status: 204 })
        }
      )
    )
    await open()
    await expect
      .element(page.getByRole("tab", { name: "Nhật ký" }))
      .toBeVisible()
    await page.getByLabelText("Vai trò của Bình").selectOptions("editor")
    await expect.poll(() => bodies).toEqual([{ role: "editor" }])
    // The list reloads after the change; wait for it before the handlers reset.
    await expect.poll(() => served.members).toBe(loadsBeforeChange + 1)
    await expect.element(page.getByLabelText("Vai trò của Bình")).toBeVisible()
  })
})

describe("OrganizationPage member removal", () => {
  test("owners confirm before removing a member", async () => {
    serve("owner")
    let removed = 0
    worker.use(
      http.delete(`*/api/v1/organizations/${ORG}/members/${OTHER}`, () => {
        removed += 1
        return new HttpResponse(null, { status: 204 })
      })
    )
    await open()
    await page.getByRole("button", { name: "Xoá Bình" }).click()
    const dialog = page.getByRole("alertdialog")
    await expect
      .element(dialog.getByText("Bình sẽ không còn truy cập tổ chức."))
      .toBeVisible()
    await dialog.getByRole("button", { name: "Huỷ" }).click()
    await expect.element(dialog).not.toBeInTheDocument()
    expect(removed).toBe(0)

    const loadsBeforeRemove = served.members
    await page.getByRole("button", { name: "Xoá Bình" }).click()
    await page
      .getByRole("alertdialog")
      .getByRole("button", { name: "Xoá", exact: true })
      .click()
    await expect.poll(() => removed).toBe(1)
    await expect.element(page.getByRole("alertdialog")).not.toBeInTheDocument()
    // The list reloads after the removal; wait for it before the handlers reset.
    await expect.poll(() => served.members).toBe(loadsBeforeRemove + 1)
  })
})

describe("OrganizationPage invitations", () => {
  test("a member's invitation waits for approval and an owner approves it", async () => {
    serve("member")
    const created: unknown[] = []
    worker.use(
      http.post(
        `*/api/v1/organizations/${ORG}/invitations`,
        async ({ request }) => {
          created.push(await request.json())
          return HttpResponse.json(invitation(), { status: 201 })
        }
      )
    )
    await open("invitations")
    await expect
      .element(page.getByLabelText("Vai trò", { exact: true }))
      .toBeVisible()
    await page.getByLabelText("Email người được mời").fill("x@example.com")
    await page.getByRole("button", { name: "Mời" }).click()
    await expect
      .poll(() => created)
      .toEqual([{ email: "x@example.com", role: "member" }])
    await expect
      .element(
        page.getByText("Lời mời đang chờ chủ sở hữu hoặc biên tập viên duyệt.")
      )
      .toBeVisible()
    await expectInvitationsReloaded()
  })

  test("owners approve pending invitations", async () => {
    serve("owner", [invitation()])
    let approved = 0
    worker.use(
      http.post(`*/api/v1/organizations/${ORG}/invitations/*/approve`, () => {
        approved += 1
        return HttpResponse.json(invitation({ status: "sent" }))
      })
    )
    await open("invitations")
    await expect.element(page.getByText("Chờ duyệt")).toBeVisible()
    await page.getByRole("button", { name: "Duyệt" }).click()
    await expect.poll(() => approved).toBe(1)
    await expectInvitationsReloaded()
  })
})

function problem({ status, code }: { status: number; code: string }) {
  return HttpResponse.json(
    { type: "about:blank", title: code, status, code },
    { status, headers: { "Content-Type": "application/problem+json" } }
  )
}

describe("OrganizationPage owner actions", () => {
  test("owners rename the organization", async () => {
    serve("owner")
    const renames: unknown[] = []
    worker.use(
      http.patch(`*/api/v1/organizations/${ORG}`, async ({ request }) => {
        const body = (await request.json()) as { name: string }
        renames.push(body)
        return HttpResponse.json({ ...organization("owner"), name: body.name })
      })
    )
    await open()
    await page.getByRole("button", { name: "Đổi tên" }).click()
    const name = page.getByLabelText("Tên tổ chức")
    await expect.element(name).toHaveValue("Khoa Dược")
    await name.fill("Khoa Dược lâm sàng")
    await page.getByRole("button", { name: "Lưu" }).click()
    await expect.poll(() => renames).toEqual([{ name: "Khoa Dược lâm sàng" }])
    await expect
      .element(page.getByRole("heading", { name: "Khoa Dược lâm sàng" }))
      .toBeVisible()
    await expect.element(page.getByText("Bình")).toBeVisible()
  })

  test("cancelling a rename keeps the name and asks nothing", async () => {
    serve("owner")
    await open()
    await page.getByRole("button", { name: "Đổi tên" }).click()
    await page.getByRole("button", { name: "Huỷ" }).click()
    await expect
      .element(page.getByRole("heading", { name: "Khoa Dược" }))
      .toBeVisible()
    await expect.element(page.getByText("Bình")).toBeVisible()
  })
})

describe("OrganizationPage log", () => {
  test("owners switch to the log tab and read the organization's events", async () => {
    serve("owner")
    worker.use(
      http.get(`*/api/v1/organizations/${ORG}/audit`, () =>
        HttpResponse.json({
          items: [
            {
              id: "e1",
              occurred_at: "2026-10-11T09:00:00Z",
              actor_user_id: ME.id,
              actor_name: "An",
              actor_was_superadmin: false,
              action: "member.left",
              organization_id: ORG,
              subject_user_id: ME.id,
              subject_name: "An",
              collection_id: null,
              details: {},
            },
          ],
          next_cursor: null,
        })
      )
    )
    await open()
    await expect.element(page.getByText("Bình")).toBeVisible()
    await page.getByRole("tab", { name: "Nhật ký" }).click()
    await expect.element(page.getByText("An đã rời tổ chức")).toBeVisible()
    await expect
      .element(page.getByRole("tab", { name: "Nhật ký" }))
      .toHaveAttribute("aria-selected", "true")
  })

  test("cancelling a delete closes the confirmation and keeps the organization", async () => {
    serve("owner")
    await open()
    await expect.element(page.getByText("Bình")).toBeVisible()
    await page.getByRole("button", { name: "Xoá tổ chức" }).click()
    await page
      .getByRole("alertdialog")
      .getByRole("button", { name: "Huỷ" })
      .click()
    await expect.element(page.getByRole("alertdialog")).not.toBeInTheDocument()
    await expect
      .element(page.getByRole("heading", { name: "Khoa Dược" }))
      .toBeVisible()
  })
})

describe("OrganizationPage delete and leave", () => {
  test("deleting needs the typed name, then returns to the organization list", async () => {
    serve("owner")
    const deletes: unknown[] = []
    worker.use(
      http.delete(`*/api/v1/organizations/${ORG}`, async ({ request }) => {
        deletes.push(await request.json())
        return new HttpResponse(null, { status: 204 })
      }),
      http.get("*/api/v1/organizations", () => HttpResponse.json([]))
    )
    await open()
    await expect.element(page.getByText("Bình")).toBeVisible()
    await page.getByRole("button", { name: "Xoá tổ chức" }).click()
    const confirm = page.getByRole("button", { name: "Xoá vĩnh viễn" })
    await expect.element(confirm).toBeDisabled()
    await page
      .getByRole("alertdialog")
      .getByLabelText("Tên tổ chức")
      .fill("Khoa")
    await expect.element(confirm).toBeDisabled()
    await page
      .getByRole("alertdialog")
      .getByLabelText("Tên tổ chức")
      .fill(" Khoa Dược ")
    await confirm.click()
    await expect.poll(() => deletes).toEqual([{ confirm_name: "Khoa Dược" }])
    await expect.element(page.getByText("Danh sách tổ chức")).toBeVisible()
  })

  test("a failed leave shows the error and keeps the confirmation open", async () => {
    serve("member")
    worker.use(
      http.post(`*/api/v1/organizations/${ORG}/leave`, () =>
        problem({ status: 403, code: "FORBIDDEN_ROLE" })
      )
    )
    await open()
    await expect.element(page.getByText("Bình")).toBeVisible()
    await page.getByRole("button", { name: "Rời tổ chức" }).click()
    await expect
      .element(
        page.getByText("Bạn sẽ không còn thấy bộ tài liệu của tổ chức này.")
      )
      .toBeVisible()
    await page.getByRole("button", { name: "Rời", exact: true }).click()
    await expect
      .element(page.getByText("Vai trò của bạn không làm được thao tác này."))
      .toBeVisible()
    await expect.element(page.getByRole("alertdialog")).toBeVisible()
    await expect
      .element(page.getByText("Danh sách tổ chức"))
      .not.toBeInTheDocument()
  })
})

describe("OrganizationPage leaving and errors", () => {
  test("leaving returns to the organization list", async () => {
    serve("member")
    let left = 0
    worker.use(
      http.post(`*/api/v1/organizations/${ORG}/leave`, () => {
        left += 1
        return new HttpResponse(null, { status: 204 })
      }),
      http.get("*/api/v1/organizations", () => HttpResponse.json([]))
    )
    await open()
    await expect.element(page.getByText("Bình")).toBeVisible()
    await page.getByRole("button", { name: "Rời tổ chức" }).click()
    await page.getByRole("button", { name: "Rời", exact: true }).click()
    await expect.poll(() => left).toBe(1)
    await expect.element(page.getByText("Danh sách tổ chức")).toBeVisible()
  })

  test("an unknown organization shows the API's error", async () => {
    worker.use(
      http.get("*/api/v1/users/me", () => HttpResponse.json(ME)),
      http.get(`*/api/v1/organizations/${ORG}`, () =>
        problem({ status: 404, code: "ORGANIZATION_NOT_FOUND" })
      )
    )
    await open()
    await expect
      .element(page.getByText("Không tìm thấy tổ chức."))
      .toBeVisible()
  })
})

/** A draft collection owned by the organization. */
const draft = {
  id: "44444444-4444-4444-8444-444444444444",
  key: "phac-do",
  title: "Phác đồ",
  visibility: "private" as const,
  owner_user_id: null,
  owner_organization_id: ORG,
  owner_name: "Khoa Dược",
  is_system: false,
  can_edit: true,
  can_set_public: false,
  current_release_id: null,
  current_release_number: null,
}

describe("OrganizationPage collections", () => {
  test("editors create a collection owned by the organization", async () => {
    serve("editor")
    const created: unknown[] = []
    let items: (typeof draft)[] = []
    worker.use(
      http.get("*/api/v1/collections", () =>
        HttpResponse.json({
          public: [],
          mine: [],
          others: [],
          organizations: [
            { organization_id: ORG, name: "Khoa Dược", role: "editor", items },
          ],
        })
      ),
      http.post("*/api/v1/collections", async ({ request }) => {
        created.push(await request.json())
        items = [draft]
        return HttpResponse.json(draft, { status: 201 })
      })
    )
    await open("collections")
    await expect
      .element(page.getByText("Tổ chức chưa có bộ tài liệu nào."))
      .toBeVisible()
    await page.getByLabelText("Tên bộ tài liệu").fill("Phác đồ")
    await page.getByRole("button", { name: "Tạo bộ tài liệu" }).click()
    await expect
      .poll(() => created)
      .toEqual([{ title: "Phác đồ", owner_organization_id: ORG }])
    await expect
      .element(page.getByRole("link", { name: /Phác đồ/ }))
      .toBeVisible()
    await expect
      .element(page.getByText("Nháp (chỉ chủ sở hữu và biên tập viên)"))
      .toBeVisible()
    await expect.element(page.getByLabelText("Tên bộ tài liệu")).toHaveValue("")
  })
})

describe("OrganizationPage collection access", () => {
  test("members see the organization's shared collections but cannot create one", async () => {
    serve("member")
    worker.use(
      http.get("*/api/v1/collections", () =>
        HttpResponse.json({
          public: [],
          mine: [],
          others: [],
          organizations: [
            {
              organization_id: ORG,
              name: "Khoa Dược",
              role: "member",
              items: [{ ...draft, visibility: "organization" }],
            },
          ],
        })
      )
    )
    await open("collections")
    await expect.element(page.getByText("Cả tổ chức")).toBeVisible()
    await expect
      .element(page.getByLabelText("Tên bộ tài liệu"))
      .not.toBeInTheDocument()
  })
})

describe("OrganizationPage collection title errors", () => {
  test("an empty title is rejected on the field", async () => {
    serve("owner")
    await open("collections")
    await page.getByRole("button", { name: "Tạo bộ tài liệu" }).click()
    await expect.element(page.getByText("Nhập tên bộ tài liệu.")).toBeVisible()
  })

  test("a rejected title shows the API's error on the field", async () => {
    serve("owner")
    worker.use(
      http.post("*/api/v1/collections", () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Unprocessable",
            status: 422,
            code: "VALIDATION_ERROR",
            errors: [
              {
                loc: ["body", "title"],
                message: "Tên quá dài.",
                type: "string_too_long",
              },
            ],
          },
          {
            status: 422,
            headers: { "Content-Type": "application/problem+json" },
          }
        )
      )
    )
    await open("collections")
    await page.getByLabelText("Tên bộ tài liệu").fill("Phác đồ")
    await page.getByRole("button", { name: "Tạo bộ tài liệu" }).click()
    await expect.element(page.getByText("Tên quá dài.")).toBeVisible()
    await expect
      .element(page.getByLabelText("Tên bộ tài liệu"))
      .toHaveAttribute("aria-invalid", "true")
  })
})
