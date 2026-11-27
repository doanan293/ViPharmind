import { HttpResponse, http } from "msw"
import { useState } from "react"
import { describe, expect, test } from "vitest"
import { page, userEvent } from "vitest/browser"

import type { AdminUserView, ConversationView } from "~/api/gen/schemas"
import { UserConversationsSheet } from "~/features/admin/components/UserConversationsSheet"

import {
  apiAssistantMessage,
  apiUserMessage,
  messagePage,
} from "../../../../tests/chat/fixtures"
import { renderWithProviders } from "../../../../tests/chat/render"
import { worker } from "../../../../tests/msw/browser"

const USER = "99999999-9999-4999-8999-999999999999"

const BINH: AdminUserView = {
  id: USER,
  display_name: "Bình",
  email: "binh@example.com",
  phone_number: null,
  is_active: true,
  is_superadmin: false,
  text_quota_bytes: null,
  collection_quota: null,
  created_at: "2026-10-11T09:00:00Z",
}

function conversation(id: string, title: string): ConversationView {
  return {
    id,
    title,
    turn_count: 2,
    created_at: "2026-10-11T09:00:00Z",
    updated_at: "2026-10-11T09:30:00Z",
    collection_ids: null,
  }
}

/** Opens the sheet for Bình; closing it shows a marker so tests can see `onClose` ran. */
function Harness() {
  const [user, setUser] = useState<AdminUserView | null>(BINH)
  return (
    <>
      {user === null ? <p>Đã đóng</p> : null}
      <UserConversationsSheet user={user} onClose={() => setUser(null)} />
    </>
  )
}

describe("UserConversationsSheet", () => {
  test("lists the user's conversations and opens one read-only, then goes back", async () => {
    worker.use(
      http.get(`*/api/v1/admin/users/${USER}/conversations`, () =>
        HttpResponse.json({
          items: [conversation("c1", "Liều paracetamol")],
          next_cursor: null,
        })
      ),
      http.get(`*/api/v1/admin/users/${USER}/conversations/c1/messages`, () =>
        HttpResponse.json(
          messagePage([
            apiUserMessage("m1", "Liều paracetamol cho người lớn?"),
            apiAssistantMessage("m2", "Người lớn dùng 500 mg mỗi lần."),
          ])
        )
      )
    )
    await renderWithProviders(<Harness />)
    await expect
      .element(page.getByRole("dialog", { name: "Hội thoại của Bình" }))
      .toBeVisible()
    await expect.element(page.getByText("Chỉ xem")).toBeVisible()
    await expect.element(page.getByText(/2 lượt hỏi/)).toBeVisible()

    await page.getByRole("button", { name: /Liều paracetamol/ }).click()
    await expect
      .element(page.getByText("Người lớn dùng 500 mg mỗi lần."))
      .toBeVisible()

    await page.getByRole("button", { name: "Về danh sách" }).click()
    await expect
      .element(page.getByRole("button", { name: /Liều paracetamol/ }))
      .toBeVisible()
  })

  test("says so when the user has no conversations, and closing calls onClose", async () => {
    worker.use(
      http.get(`*/api/v1/admin/users/${USER}/conversations`, () =>
        HttpResponse.json({ items: [], next_cursor: null })
      )
    )
    await renderWithProviders(<Harness />)
    await expect
      .element(page.getByText("Người dùng chưa có hội thoại nào."))
      .toBeVisible()
    await userEvent.keyboard("{Escape}")
    await expect.element(page.getByText("Đã đóng")).toBeVisible()
  })

  test("loads more conversations on demand", async () => {
    worker.use(
      http.get(`*/api/v1/admin/users/${USER}/conversations`, ({ request }) =>
        new URL(request.url).searchParams.get("cursor") === null
          ? HttpResponse.json({
              items: [conversation("c1", "Hội thoại một")],
              next_cursor: "p2",
            })
          : HttpResponse.json({
              items: [conversation("c2", "Hội thoại hai")],
              next_cursor: null,
            })
      )
    )
    await renderWithProviders(<Harness />)
    await page.getByRole("button", { name: "Tải thêm" }).click()
    await expect
      .element(page.getByRole("button", { name: /Hội thoại hai/ }))
      .toBeVisible()
  })
})
