import { HttpResponse, http } from "msw"
import { MemoryRouter } from "react-router"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { DocumentView } from "~/api/gen/schemas"
import { Toaster } from "~/components/ui/toast"
import { DocumentsTab } from "~/features/collections/components/DocumentsTab"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const ID = "44444444-4444-4444-8444-444444444444"
const DOC = "66666666-6666-4666-8666-666666666666"
const DOCUMENTS = `*/api/v1/collections/${ID}/documents`
const HTTP_FORBIDDEN = 403

const PARACETAMOL: DocumentView = {
  id: DOC,
  collection_id: ID,
  key: "paracetamol",
  title: "Paracetamol",
  kind: "drug_monograph",
  source_title: "",
  source_url: null,
  char_count: 1200,
  updated_at: "2026-10-11T09:00:00Z",
}

async function open(editable: boolean) {
  await render(
    <TestProviders>
      <Toaster>
        <MemoryRouter>
          <DocumentsTab collectionId={ID} editable={editable} />
        </MemoryRouter>
      </Toaster>
    </TestProviders>
  )
}

describe("DocumentsTab", () => {
  test("an empty collection says so and offers editors to add a document", async () => {
    worker.use(http.get(DOCUMENTS, () => HttpResponse.json([])))
    await open(true)
    await expect.element(page.getByText("Chưa có tài liệu nào.")).toBeVisible()
    await expect
      .element(page.getByRole("link", { name: "Thêm tài liệu" }))
      .toHaveAttribute("href", `/collections/${ID}/documents/new`)
  })

  test("viewers see titles as plain text without delete buttons", async () => {
    worker.use(http.get(DOCUMENTS, () => HttpResponse.json([PARACETAMOL])))
    await open(false)
    await expect.element(page.getByText("Paracetamol")).toBeVisible()
    await expect
      .element(page.getByRole("link", { name: "Paracetamol" }))
      .not.toBeInTheDocument()
    await expect
      .element(page.getByRole("button", { name: "Xoá Paracetamol" }))
      .not.toBeInTheDocument()
  })

  test("deleting a document removes it from the list", async () => {
    let documents = [PARACETAMOL]
    worker.use(
      http.get(DOCUMENTS, () => HttpResponse.json(documents)),
      http.delete(`${DOCUMENTS}/${DOC}`, () => {
        documents = []
        return new HttpResponse(null, { status: 204 })
      })
    )
    await open(true)
    await page.getByRole("button", { name: "Xoá Paracetamol" }).click()
    await expect.element(page.getByText("Chưa có tài liệu nào.")).toBeVisible()
  })

  test("a refused delete shows the error and keeps the document", async () => {
    worker.use(
      http.get(DOCUMENTS, () => HttpResponse.json([PARACETAMOL])),
      http.delete(`${DOCUMENTS}/${DOC}`, () =>
        HttpResponse.json(
          {
            type: "urn:pharma-agent:problem:forbidden-role",
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
    await open(true)
    await page.getByRole("button", { name: "Xoá Paracetamol" }).click()
    await expect
      .element(page.getByText("Vai trò của bạn không làm được thao tác này."))
      .toBeVisible()
    await expect
      .element(page.getByRole("link", { name: "Paracetamol" }))
      .toBeVisible()
  })
})
