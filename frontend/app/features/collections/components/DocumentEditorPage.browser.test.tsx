import { http, HttpResponse } from "msw"
import { createRoutesStub } from "react-router"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { CollectionView } from "~/api/gen/schemas"
import { Toaster } from "~/components/ui/toast"
import { DocumentEditorPage } from "~/features/collections/components/DocumentEditorPage"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const ID = "44444444-4444-4444-8444-444444444444"
const DOC = "66666666-6666-4666-8666-666666666666"

const COLLECTION: CollectionView = {
  id: ID,
  key: "u-1234abcd",
  title: "Ghi chú của tôi",
  visibility: "private",
  owner_user_id: "77777777-7777-4777-8777-777777777777",
  owner_organization_id: null,
  owner_name: "An",
  is_system: false,
  can_edit: true,
  can_set_public: false,
  current_release_id: null,
  current_release_number: null,
}

function serve() {
  worker.use(
    http.get(`*/api/v1/collections/${ID}`, () => HttpResponse.json(COLLECTION)),
    http.get("*/api/v1/collections/quota", () =>
      HttpResponse.json({
        text_used: 1000,
        text_limit: 1000000,
        collections_used: 1,
        collections_limit: 5,
      })
    )
  )
}

async function open(documentId = "new") {
  const Stub = createRoutesStub([
    {
      path: "/collections/:collectionId/documents/:documentId",
      Component: () => (
        <DocumentEditorPage collectionId={ID} documentId={documentId} />
      ),
    },
    { path: "/collections/:collectionId/:tab?", Component: () => <p>Bộ</p> },
  ])
  await render(
    <TestProviders>
      <Toaster>
        <Stub initialEntries={[`/collections/${ID}/documents/${documentId}`]} />
      </Toaster>
    </TestProviders>
  )
}

describe("DocumentEditorPage", () => {
  test("creates a document from the form", async () => {
    serve()
    const bodies: unknown[] = []
    worker.use(
      http.post(`*/api/v1/collections/${ID}/documents`, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json({ id: DOC }, { status: 201 })
      })
    )
    await open()
    await page.getByLabelText("Tiêu đề", { exact: true }).fill("Paracetamol")
    await page.getByLabelText("Loại tài liệu").selectOptions("leaflet")
    await page.getByLabelText("Nguồn", { exact: true }).fill("Dược thư")
    await page.getByRole("textbox", { name: "Nội dung" }).click()
    await page.getByRole("textbox", { name: "Nội dung" }).fill("Giảm đau")
    await page.getByRole("button", { name: "Lưu tài liệu" }).click()
    await expect.poll(() => bodies).toHaveLength(1)
    expect(bodies[0]).toEqual({
      title: "Paracetamol",
      kind: "leaflet",
      source_title: "Dược thư",
      source_url: null,
      markdown: "Giảm đau",
    })
    await expect.element(page.getByText("Bộ")).toBeVisible()
  })

  test("an uploaded Markdown file fills the form", async () => {
    serve()
    worker.use(
      http.post(`*/api/v1/collections/${ID}/documents/upload`, () =>
        HttpResponse.json({
          title: "Ibuprofen",
          markdown: "# Ibuprofen\n\nKháng viêm",
          char_count: 22,
        })
      )
    )
    await open()
    const file = new File(["# Ibuprofen\n\nKháng viêm"], "ibuprofen.md", {
      type: "text/markdown",
    })
    await page.getByLabelText("Tải lên .md hoặc .txt").upload(file)
    await expect
      .element(page.getByLabelText("Tiêu đề", { exact: true }))
      .toHaveValue("Ibuprofen")
    await expect
      .element(
        page.getByRole("textbox", { name: "Nội dung" }).getByText("Kháng viêm")
      )
      .toBeVisible()
  })
})
