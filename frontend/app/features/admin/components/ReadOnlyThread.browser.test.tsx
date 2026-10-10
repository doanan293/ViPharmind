import { http, HttpResponse } from "msw"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"

import { ReadOnlyThread } from "~/features/admin/components/ReadOnlyThread"

import {
  apiAssistantMessage,
  apiUserMessage,
  messagePage,
} from "../../../../tests/chat/fixtures"
import { renderWithProviders } from "../../../../tests/chat/render"
import { worker } from "../../../../tests/msw/browser"

describe("ReadOnlyThread", () => {
  test("shows a user's conversation without feedback actions", async () => {
    worker.use(
      http.get("*/api/v1/admin/users/u1/conversations/c1/messages", () =>
        HttpResponse.json(
          messagePage([
            apiUserMessage("m1", "Liều paracetamol cho người lớn?"),
            apiAssistantMessage("m2", "Người lớn dùng 500 mg mỗi lần."),
          ])
        )
      )
    )
    await renderWithProviders(
      <ReadOnlyThread userId="u1" conversationId="c1" />
    )
    await expect
      .element(page.getByText("Liều paracetamol cho người lớn?"))
      .toBeVisible()
    await expect
      .element(page.getByText("Người lớn dùng 500 mg mỗi lần."))
      .toBeVisible()
    await expect
      .element(page.getByRole("button", { name: "Hữu ích" }))
      .not.toBeInTheDocument()
  })
})
