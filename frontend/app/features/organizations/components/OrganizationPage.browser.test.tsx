import { http, HttpResponse } from "msw"
import { createRoutesStub } from "react-router"
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

const served = { members: 0 }

function serve(
  role: OrganizationView["role"],
  invitations: InvitationView[] = []
) {
  served.members = 0
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
    http.get(`*/api/v1/organizations/${ORG}/invitations`, () =>
      HttpResponse.json(invitations)
    ),
    http.get("*/api/v1/collections", () =>
      HttpResponse.json({ public: [], organizations: [], mine: [], others: [] })
    )
  )
}

async function open(tab = "members") {
  const Stub = createRoutesStub([
    {
      path: "/organizations/:organizationId/:tab?",
      Component: () => <OrganizationPage organizationId={ORG} tab={tab} />,
    },
  ])
  await render(
    <TestProviders>
      <Toaster>
        <Stub initialEntries={[`/organizations/${ORG}/${tab}`]} />
      </Toaster>
    </TestProviders>
  )
}

describe("OrganizationPage", () => {
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
  })
})
