import { HttpResponse, http } from "msw"
import { createRoutesStub, useParams } from "react-router"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { CollectionView, DocumentDetail } from "~/api/gen/schemas"
import { Toaster } from "~/components/ui/toast"
import { DocumentEditorPage } from "~/features/collections/components/DocumentEditorPage"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const ID = "44444444-4444-4444-8444-444444444444"
const DOC = "66666666-6666-4666-8666-666666666666"
const DOCUMENT_URL = `*/api/v1/collections/${ID}/documents/${DOC}`
const UPLOAD_URL = `*/api/v1/collections/${ID}/documents/upload`
const HTTP_NOT_FOUND = 404
const HTTP_UNPROCESSABLE = 422
const PROBLEM_HEADERS = { "Content-Type": "application/problem+json" }

const STORED: DocumentDetail = {
  id: DOC,
  collection_id: ID,
  key: "paracetamol",
  title: "Paracetamol",
  kind: "drug_monograph",
  source_title: "Dược thư",
  source_url: null,
  markdown: "Giảm đau",
  char_count: 8,
  updated_at: "2026-10-11T09:00:00Z",
}

/** A problem response saying the collection or document is gone. */
function notFound() {
  return HttpResponse.json(
    {
      type: "urn:pharma-agent:problem:collection-not-found",
      title: "Not found",
      status: HTTP_NOT_FOUND,
      code: "COLLECTION_NOT_FOUND",
    },
    { status: HTTP_NOT_FOUND, headers: PROBLEM_HEADERS }
  )
}

/** Waits for the text quota, so its request does not outlive the test. */
async function quotaShown() {
  await expect.element(page.getByText(/^Đã dùng/)).toBeVisible()
}

/** The file a user picks to fill the form. */
const UPLOADED = new File(["# Ibuprofen\n\nKháng viêm"], "ibuprofen.md", {
  type: "text/markdown",
})

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

/** Renders the editor for the route's document, as the real route module does. */
function DocumentRoute() {
  const { documentId } = useParams()
  if (documentId === undefined) return null
  return <DocumentEditorPage collectionId={ID} documentId={documentId} />
}

/** Stands in for the collection page the editor returns to. */
function CollectionStub() {
  return <p>Bộ</p>
}

async function open(documentId = "new") {
  const Stub = createRoutesStub([
    {
      path: "/collections/:collectionId/documents/:documentId",
      Component: DocumentRoute,
    },
    { path: "/collections/:collectionId/:tab?", Component: CollectionStub },
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

  test("the upload control is a labelled button, not the browser's file picker", async () => {
    serve()
    await open()
    // The native file input shows browser chrome ("Choose File") in the browser's language.
    // Only a real button shows its label as text; the native input shows "Choose File".
    await expect.element(page.getByText("Tải lên .md hoặc .txt")).toBeVisible()
    await quotaShown()
  })
})

describe("DocumentEditorPage existing documents", () => {
  test("saving a stored document replaces it and returns to the list", async () => {
    serve()
    const bodies: unknown[] = []
    worker.use(
      http.get(DOCUMENT_URL, () => HttpResponse.json(STORED)),
      http.put(DOCUMENT_URL, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json(STORED)
      })
    )
    await open(DOC)
    const title = page.getByLabelText("Tiêu đề", { exact: true })
    await expect.element(title).toHaveValue("Paracetamol")
    await title.fill("Paracetamol 500")
    await page.getByRole("button", { name: "Lưu tài liệu" }).click()
    await expect.element(page.getByText("Đã lưu tài liệu.")).toBeVisible()
    await expect.element(page.getByText("Bộ")).toBeVisible()
    expect(bodies).toEqual([
      {
        title: "Paracetamol 500",
        kind: "drug_monograph",
        source_title: "Dược thư",
        source_url: null,
        markdown: "Giảm đau",
      },
    ])
  })

  test("a document that cannot be loaded shows the error", async () => {
    serve()
    worker.use(http.get(DOCUMENT_URL, notFound))
    await open(DOC)
    await expect
      .element(page.getByText("Không tìm thấy bộ tài liệu."))
      .toBeVisible()
  })

  test("a collection that cannot be loaded shows the error", async () => {
    worker.use(http.get(`*/api/v1/collections/${ID}`, notFound))
    await open()
    await expect
      .element(page.getByText("Không tìm thấy bộ tài liệu."))
      .toBeVisible()
  })
})

describe("DocumentEditorPage save errors", () => {
  test("a field the API rejects shows its message on that field", async () => {
    serve()
    worker.use(http.get(DOCUMENT_URL, () => HttpResponse.json(STORED)))
    worker.use(
      http.put(DOCUMENT_URL, () =>
        HttpResponse.json(
          {
            type: "urn:pharma-agent:problem:validation-error",
            title: "Validation error",
            status: HTTP_UNPROCESSABLE,
            code: "VALIDATION_ERROR",
            errors: [
              {
                loc: ["body", "title"],
                message: "Tiêu đề đã có",
                type: "value_error",
              },
            ],
          },
          { status: HTTP_UNPROCESSABLE, headers: PROBLEM_HEADERS }
        )
      )
    )
    await open(DOC)
    await expect
      .element(page.getByLabelText("Tiêu đề", { exact: true }))
      .toHaveValue("Paracetamol")
    await page.getByRole("button", { name: "Lưu tài liệu" }).click()
    await expect.element(page.getByText("Tiêu đề đã có")).toBeVisible()
    await quotaShown()
  })

  test("any other refusal shows under the form", async () => {
    serve()
    worker.use(
      http.get(DOCUMENT_URL, () => HttpResponse.json(STORED)),
      http.put(DOCUMENT_URL, notFound)
    )
    await open(DOC)
    await expect
      .element(page.getByLabelText("Tiêu đề", { exact: true }))
      .toHaveValue("Paracetamol")
    await page.getByRole("button", { name: "Lưu tài liệu" }).click()
    await expect
      .element(page.getByText("Không tìm thấy bộ tài liệu."))
      .toBeVisible()
    await quotaShown()
  })
})

describe("DocumentEditorPage uploads", () => {
  test("uploading over typed content asks first and replaces it on confirm", async () => {
    serve()
    worker.use(
      http.post(UPLOAD_URL, () =>
        HttpResponse.json({
          title: "Ibuprofen",
          markdown: "# Ibuprofen\n\nKháng viêm",
          char_count: 22,
        })
      )
    )
    await open()
    const title = page.getByLabelText("Tiêu đề", { exact: true })
    await title.fill("Bản nháp")
    await page.getByLabelText("Tải lên .md hoặc .txt").upload(UPLOADED)
    await expect
      .element(page.getByText("Thay nội dung hiện tại bằng tệp này?"))
      .toBeVisible()
    await page.getByRole("button", { name: "Lưu", exact: true }).click()
    await expect.element(title).toHaveValue("Ibuprofen")
    await quotaShown()
  })

  test("declining the replacement keeps the typed content", async () => {
    serve()
    worker.use(
      http.post(UPLOAD_URL, () =>
        HttpResponse.json({ title: "Ibuprofen", markdown: "x", char_count: 1 })
      )
    )
    await open()
    const title = page.getByLabelText("Tiêu đề", { exact: true })
    await title.fill("Bản nháp")
    await page.getByLabelText("Tải lên .md hoặc .txt").upload(UPLOADED)
    await page.getByRole("button", { name: "Huỷ" }).click()
    await expect.element(title).toHaveValue("Bản nháp")
    await quotaShown()
  })

  test("a refused upload shows the error", async () => {
    serve()
    worker.use(http.post(UPLOAD_URL, notFound))
    await open()
    await page.getByLabelText("Tải lên .md hoặc .txt").upload(UPLOADED)
    await expect
      .element(page.getByText("Không tìm thấy bộ tài liệu."))
      .toBeVisible()
    await quotaShown()
  })
})
