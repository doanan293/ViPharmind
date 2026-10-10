import { http, HttpResponse } from "msw"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { CollectionView, ConversationView } from "~/api/gen/schemas"
import { Toaster } from "~/components/ui/toast"
import { ConversationSources } from "~/features/chat/components/SourcesPopover"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const CONVERSATION = "88888888-8888-4888-8888-888888888888"

function collection(id: string, title: string): CollectionView {
  return {
    id,
    key: id,
    title,
    visibility: "private",
    owner_user_id: null,
    owner_organization_id: null,
    owner_name: "",
    is_system: false,
    can_edit: false,
    can_set_public: false,
    current_release_id: null,
    current_release_number: null,
  }
}

function conversation(collectionIds: string[] | null): ConversationView {
  return {
    id: CONVERSATION,
    title: "Hỏi thuốc",
    turn_count: 1,
    created_at: "2026-10-11T09:00:00Z",
    updated_at: "2026-10-11T09:00:00Z",
    collection_ids: collectionIds,
  }
}

describe("ConversationSources", () => {
  test("narrows the conversation to chosen collections and back to all", async () => {
    let current: string[] | null = null
    const patches: unknown[] = []
    worker.use(
      http.get(`*/api/v1/conversations/${CONVERSATION}`, () =>
        HttpResponse.json(conversation(current))
      ),
      http.get("*/api/v1/collections", () =>
        HttpResponse.json({
          public: [collection("c-pub", "Dược thư quốc gia")],
          organizations: [
            {
              organization_id: "o1",
              name: "Khoa Dược",
              role: "member",
              items: [collection("c-org", "Phác đồ khoa")],
            },
          ],
          mine: [collection("c-mine", "Ghi chú")],
          others: [],
        })
      ),
      http.patch(
        `*/api/v1/conversations/${CONVERSATION}`,
        async ({ request }) => {
          const body = await request.json()
          patches.push(body)
          current =
            typeof body === "object" &&
            body !== null &&
            "collection_ids" in body &&
            Array.isArray(body.collection_ids)
              ? body.collection_ids.map(String)
              : null
          return HttpResponse.json(conversation(current))
        }
      )
    )
    await render(
      <TestProviders>
        <Toaster>
          <ConversationSources conversationId={CONVERSATION} />
        </Toaster>
      </TestProviders>
    )
    await page.getByRole("combobox", { name: "Nguồn" }).click()
    await expect.element(page.getByText("Công khai")).toBeVisible()
    await expect.element(page.getByText("Khoa Dược")).toBeVisible()
    await expect.element(page.getByText("Của tôi")).toBeVisible()

    await page.getByRole("option", { name: "Phác đồ khoa" }).click()
    await expect.poll(() => patches).toEqual([{ collection_ids: ["c-org"] }])
    await expect
      .element(page.getByRole("combobox", { name: "Nguồn: 1" }))
      .toBeVisible()

    await page
      .getByRole("button", { name: "Tất cả nguồn tôi được thấy" })
      .click()
    await expect
      .poll(() => patches)
      .toEqual([{ collection_ids: ["c-org"] }, { collection_ids: null }])
    await expect
      .element(page.getByRole("combobox", { name: "Nguồn", exact: true }))
      .toBeVisible()
  })
})
