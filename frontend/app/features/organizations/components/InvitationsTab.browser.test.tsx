import { HttpResponse, http } from "msw"
import { afterEach, describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { InvitationView } from "~/api/gen/schemas"
import { Toaster } from "~/components/ui/toast"
import { InvitationsTab } from "~/features/organizations/components/InvitationsTab"
import type { Viewer } from "~/features/organizations/lib/roles"

import { worker } from "../../../../tests/msw/browser"
import {
  createTestQueryClient,
  TestProviders,
} from "../../../../tests/utils/providers"

const ORG = "11111111-1111-4111-8111-111111111111"
const ME = "0b8f7a52-5d4e-4c7b-9a51-3f7d1c2b9e10"
const OTHER = "22222222-2222-4222-8222-222222222222"
const HTTP_CREATED = 201
const HTTP_CONFLICT = 409
const HTTP_FORBIDDEN = 403

const OWNER: Viewer = { role: "owner", superadmin: false }
const MEMBER: Viewer = { role: "member", superadmin: false }
const OUTSIDER: Viewer = { role: null, superadmin: false }

function invitation(
  id: string,
  overrides: Partial<InvitationView> = {}
): InvitationView {
  return {
    id,
    organization_id: ORG,
    email: `${id}@example.com`,
    role: "member",
    status: "sent",
    invited_by: OTHER,
    invited_by_name: "Bình",
    created_at: "2026-10-11T09:00:00Z",
    expires_at: "2026-10-18T09:00:00Z",
    ...overrides,
  }
}

function problem(status: number, code: string) {
  return HttpResponse.json(
    { type: "about:blank", title: code, status, code },
    { status, headers: { "Content-Type": "application/problem+json" } }
  )
}

/** Every invitation action the tab sent, as `<action> <invitation id>`. */
let actions: string[] = []
/** How often the list was loaded, counted per test. */
let loads = { count: 0 }

/** Serves `invitations` and records approve, reject, revoke and resend calls. */
function serve(invitations: InvitationView[]) {
  actions = []
  loads = { count: 0 }
  const counted = loads
  const recorded = actions
  worker.use(
    http.get(`*/api/v1/organizations/${ORG}/invitations`, () => {
      counted.count += 1
      return HttpResponse.json(invitations)
    }),
    http.post(
      `*/api/v1/organizations/${ORG}/invitations/:invitationId/:action`,
      ({ params }) => {
        recorded.push(`${String(params.action)} ${String(params.invitationId)}`)
        return new HttpResponse(null, { status: 204 })
      }
    )
  )
}

/** The query client of the rendered tab. */
let client = createTestQueryClient()

// Each action reloads the list. Wait until every request has been answered while the test's
// handlers are still installed; a reload landing after the reset fails as unhandled.
afterEach(async () => {
  await expect.poll(() => client.isFetching() + client.isMutating()).toBe(0)
})

async function open(viewer: Viewer) {
  client = createTestQueryClient()
  await render(
    <TestProviders client={client}>
      <Toaster>
        <InvitationsTab
          organizationId={ORG}
          viewer={viewer}
          currentUserId={ME}
        />
      </Toaster>
    </TestProviders>
  )
}

describe("InvitationsTab invite form", () => {
  test("owners invite with a chosen role and see that the invitation was sent", async () => {
    serve([])
    const created: unknown[] = []
    worker.use(
      http.post(
        `*/api/v1/organizations/${ORG}/invitations`,
        async ({ request }) => {
          created.push(await request.json())
          return HttpResponse.json(invitation("new", { role: "editor" }), {
            status: HTTP_CREATED,
          })
        }
      )
    )
    await open(OWNER)
    await expect.element(page.getByText("Chưa có lời mời nào.")).toBeVisible()
    await page.getByLabelText("Email người được mời").fill("c@example.com")
    await page
      .getByLabelText("Vai trò", { exact: true })
      .selectOptions("editor")
    await page.getByRole("button", { name: "Mời" }).click()
    await expect
      .poll(() => created)
      .toEqual([{ email: "c@example.com", role: "editor" }])
    await expect.element(page.getByText("Đã gửi lời mời.")).toBeVisible()
    await expect
      .element(page.getByLabelText("Email người được mời"))
      .toHaveValue("")
    await expect.poll(() => loads.count).toBe(2)
  })

  test("a refused invitation shows the API's error under the email", async () => {
    serve([])
    worker.use(
      http.post(`*/api/v1/organizations/${ORG}/invitations`, () =>
        problem(HTTP_CONFLICT, "INVITATION_ALREADY_OPEN")
      )
    )
    await open(OWNER)
    await page.getByLabelText("Email người được mời").fill("c@example.com")
    await page.getByRole("button", { name: "Mời" }).click()
    await expect
      .element(page.getByText("Email này đã có một lời mời đang chờ."))
      .toBeVisible()
  })

  test("someone outside the organization sees the list but no invite form", async () => {
    serve([invitation("i1")])
    await open(OUTSIDER)
    await expect.element(page.getByText(/^i1@example\.com/)).toBeVisible()
    await expect
      .element(page.getByLabelText("Email người được mời"))
      .not.toBeInTheDocument()
    await expect.element(page.getByRole("button")).not.toBeInTheDocument()
  })
})

describe("InvitationsTab editor actions", () => {
  test("owners reject pending, resend and revoke sent, and only resend expired invitations", async () => {
    serve([
      invitation("pending", { status: "pending_approval" }),
      invitation("sent"),
      invitation("expired", { status: "expired" }),
      invitation("accepted", { status: "accepted" }),
    ])
    await open(OWNER)
    await expect.element(page.getByText("Đã nhận")).toBeVisible()
    await page.getByRole("button", { name: "Từ chối" }).click()
    await expect.poll(() => actions).toEqual(["reject pending"])
    await expect.poll(() => loads.count).toBe(2)

    const resend = page.getByRole("button", { name: "Gửi lại" })
    await expect.element(resend.nth(1)).toBeVisible()
    await resend.nth(0).click()
    await page.getByRole("button", { name: "Thu hồi" }).click()
    await resend.nth(1).click()
    await expect
      .poll(() => [...actions].sort((a, b) => a.localeCompare(b)))
      .toEqual([
        "reject pending",
        "resend expired",
        "resend sent",
        "revoke sent",
      ])
    await expect
      .poll(() => page.getByRole("button", { name: "Thu hồi" }).all().length)
      .toBe(1)
  })
})

describe("InvitationsTab inviter actions", () => {
  test("members act only on their own invitations: revoke while pending, resend once sent", async () => {
    serve([
      invitation("mine-pending", {
        status: "pending_approval",
        invited_by: ME,
      }),
      invitation("mine-sent", { invited_by: ME }),
      invitation("theirs-pending", { status: "pending_approval" }),
      invitation("theirs-sent"),
    ])
    await open(MEMBER)
    await expect
      .element(page.getByText(/^theirs-sent@example\.com/))
      .toBeVisible()
    await expect
      .element(page.getByRole("button", { name: "Duyệt" }))
      .not.toBeInTheDocument()
    await expect
      .poll(() => page.getByRole("button", { name: "Gửi lại" }).all().length)
      .toBe(1)
    await expect
      .poll(() => page.getByRole("button", { name: "Thu hồi" }).all().length)
      .toBe(2)
    await page.getByRole("button", { name: "Thu hồi" }).first().click()
    await expect.poll(() => actions).toEqual(["revoke mine-pending"])
    await expect.poll(() => loads.count).toBe(2)
  })

  test("a refused action shows the API's error", async () => {
    serve([invitation("mine", { invited_by: ME })])
    worker.use(
      http.post(`*/api/v1/organizations/${ORG}/invitations/mine/resend`, () =>
        problem(HTTP_FORBIDDEN, "FORBIDDEN_ROLE")
      )
    )
    await open(MEMBER)
    await page.getByRole("button", { name: "Gửi lại" }).click()
    await expect
      .element(page.getByText("Vai trò của bạn không làm được thao tác này."))
      .toBeVisible()
  })
})
