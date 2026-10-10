import { http, HttpResponse } from "msw"
import { createRoutesStub } from "react-router"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { InvitationLanding } from "~/features/organizations/components/InvitationLanding"

import { worker } from "../../../../tests/msw/browser"
import { accountView } from "../../../../tests/utils/account"
import { TestProviders } from "../../../../tests/utils/providers"

const TOKEN = "a".repeat(43)
const ORG = "11111111-1111-4111-8111-111111111111"

function preview() {
  return http.get(`*/api/v1/invitations/${TOKEN}`, () =>
    HttpResponse.json({
      organization_name: "Khoa Dược",
      inviter_name: "An",
      role: "editor",
      email_hint: "b**@example.com",
    })
  )
}

function signedOut() {
  return http.get("*/api/v1/users/me", () =>
    HttpResponse.json(
      { code: "UNAUTHORIZED", title: "Unauthorized", status: 401 },
      { status: 401, headers: { "Content-Type": "application/problem+json" } }
    )
  )
}

async function open(signOut: () => Promise<void> = async () => undefined) {
  const Stub = createRoutesStub([
    {
      path: "/invitations/:token",
      Component: () => <InvitationLanding token={TOKEN} onSignOut={signOut} />,
    },
    { path: "/organizations/:id", Component: () => <p>organization-page</p> },
  ])
  await render(
    <TestProviders>
      <Stub initialEntries={[`/invitations/${TOKEN}`]} />
    </TestProviders>
  )
}

describe("InvitationLanding", () => {
  test("asks a visitor to sign in and come back", async () => {
    worker.use(preview(), signedOut())
    await open()
    await expect
      .element(
        page.getByText(
          "An mời bạn tham gia Khoa Dược với vai trò Biên tập viên."
        )
      )
      .toBeVisible()
    await expect
      .element(page.getByRole("link", { name: "Đăng nhập để nhận lời mời" }))
      .toHaveAttribute("href", `/login?next=%2Finvitations%2F${TOKEN}`)
  })

  test("joins and opens the organization", async () => {
    worker.use(
      preview(),
      http.get("*/api/v1/users/me", () => HttpResponse.json(accountView())),
      http.post(`*/api/v1/invitations/${TOKEN}/accept`, () =>
        HttpResponse.json({
          id: ORG,
          name: "Khoa Dược",
          role: "editor",
          member_count: 2,
          created_at: "2026-10-11T09:00:00Z",
        })
      )
    )
    await open()
    await page.getByRole("button", { name: "Tham gia" }).click()
    await expect.element(page.getByText("organization-page")).toBeVisible()
  })

  test("explains a mismatched email and offers to sign out", async () => {
    let signedOutCalls = 0
    worker.use(
      preview(),
      http.get("*/api/v1/users/me", () => HttpResponse.json(accountView())),
      http.post(`*/api/v1/invitations/${TOKEN}/accept`, () =>
        HttpResponse.json(
          { code: "INVITATION_EMAIL_MISMATCH", title: "Conflict", status: 409 },
          {
            status: 409,
            headers: { "Content-Type": "application/problem+json" },
          }
        )
      )
    )
    await open(async () => {
      signedOutCalls += 1
    })
    await page.getByRole("button", { name: "Tham gia" }).click()
    await expect
      .element(page.getByText(/Lời mời này dành cho b\*\*@example\.com/))
      .toBeVisible()
    await page.getByRole("button", { name: "Đăng xuất" }).click()
    expect(signedOutCalls).toBe(1)
  })

  test("says when the link no longer works", async () => {
    worker.use(
      signedOut(),
      http.get(`*/api/v1/invitations/${TOKEN}`, () =>
        HttpResponse.json(
          { code: "INVITATION_NOT_FOUND", title: "Not Found", status: 404 },
          {
            status: 404,
            headers: { "Content-Type": "application/problem+json" },
          }
        )
      )
    )
    await open()
    await expect
      .element(
        page.getByText("Lời mời không còn hiệu lực. Hãy nhờ người mời gửi lại.")
      )
      .toBeVisible()
  })
})
