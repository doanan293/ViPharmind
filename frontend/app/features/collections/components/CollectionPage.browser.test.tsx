import { HttpResponse, http } from "msw"
import { createRoutesStub, useParams } from "react-router"
import { describe, expect, test } from "vitest"
import { page, userEvent } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { CollectionView, JobView } from "~/api/gen/schemas"
import { Toaster } from "~/components/ui/toast"
import { CollectionPage } from "~/features/collections/components/CollectionPage"

import { worker } from "../../../../tests/msw/browser"
import { accountView } from "../../../../tests/utils/account"
import { TestProviders } from "../../../../tests/utils/providers"

const ID = "44444444-4444-4444-8444-444444444444"
const COLLECTION_URL = `*/api/v1/collections/${ID}`
const HTTP_NOT_FOUND = 404

/** A problem response the API sends when the collection is gone. */
function notFound() {
  return HttpResponse.json(
    {
      type: "urn:pharma-agent:problem:collection-not-found",
      title: "Not found",
      status: HTTP_NOT_FOUND,
      code: "COLLECTION_NOT_FOUND",
    },
    {
      status: HTTP_NOT_FOUND,
      headers: { "Content-Type": "application/problem+json" },
    }
  )
}

/** Stands in for the collection list a deleted collection returns to. */
function CollectionsStub() {
  return <p>Danh sách bộ tài liệu</p>
}

function collection(overrides: Partial<CollectionView> = {}): CollectionView {
  return {
    id: ID,
    key: "o-1234abcd",
    title: "Thuốc tim mạch",
    visibility: "private",
    owner_user_id: null,
    owner_organization_id: "11111111-1111-4111-8111-111111111111",
    owner_name: "Khoa Dược",
    is_system: false,
    can_edit: true,
    can_set_public: false,
    current_release_id: null,
    current_release_number: null,
    ...overrides,
  }
}

function job(overrides: Partial<JobView> = {}): JobView {
  return {
    id: "55555555-5555-4555-8555-555555555555",
    collection_id: ID,
    status: "queued",
    step: "bundle",
    progress: 0,
    error: null,
    attempts: 0,
    release_number: null,
    created_at: "2026-10-11T09:00:00Z",
    started_at: null,
    finished_at: null,
    ...overrides,
  }
}

function serve(view: CollectionView, superadmin = false) {
  worker.use(
    http.get("*/api/v1/users/me", () =>
      HttpResponse.json(accountView({ is_superadmin: superadmin }))
    ),
    http.get(`*/api/v1/collections/${ID}`, () => HttpResponse.json(view)),
    http.get(`*/api/v1/collections/${ID}/documents`, () =>
      HttpResponse.json([
        {
          id: "d1",
          collection_id: ID,
          key: "paracetamol",
          title: "Paracetamol",
          kind: "drug_monograph",
          source_title: "",
          source_url: null,
          char_count: 1200,
          updated_at: "2026-10-11T09:00:00Z",
        },
      ])
    ),
    http.get(`*/api/v1/collections/${ID}/glossary`, () =>
      HttpResponse.json([
        { term: "ADR", vietnamese_expansions: ["phản ứng có hại"] },
      ])
    ),
    http.get(`*/api/v1/collections/${ID}/releases`, () => HttpResponse.json([]))
  )
}

/** Renders the page for the route's tab, as the real route module does. */
function CollectionRoute() {
  const { tab } = useParams()
  return <CollectionPage collectionId={ID} tab={tab} />
}

async function open(tab = "documents") {
  const Stub = createRoutesStub([
    { path: "/collections", Component: CollectionsStub },
    {
      path: "/collections/:collectionId/:tab?",
      Component: CollectionRoute,
    },
  ])
  await render(
    <TestProviders>
      <Toaster>
        <Stub initialEntries={[`/collections/${ID}/${tab}`]} />
      </Toaster>
    </TestProviders>
  )
}

describe("CollectionPage access", () => {
  test("only superadmins can make a collection public", async () => {
    serve(collection())
    await open()
    await expect.element(page.getByText("Paracetamol")).toBeVisible()
    const select = page.getByLabelText("Ai được thấy")
    await expect.element(select).toBeVisible()
    await expect
      .element(page.getByRole("option", { name: "Công khai" }))
      .not.toBeInTheDocument()
  })

  test("the system corpus shows only its releases", async () => {
    serve(
      collection({ is_system: true, can_edit: false, visibility: "public" })
    )
    await open("releases")
    await expect
      .element(page.getByRole("tab", { name: "Bản phát hành" }))
      .toBeVisible()
    await expect
      .element(page.getByRole("tab", { name: "Tài liệu" }))
      .not.toBeInTheDocument()
    await expect
      .element(page.getByRole("button", { name: "Xuất bản" }))
      .not.toBeInTheDocument()
    // Wait for the release list so its request does not outlive the test.
    await expect.element(page.getByText("Chưa xuất bản lần nào.")).toBeVisible()
  })
})

describe("CollectionPage glossary", () => {
  test("the glossary is saved as a whole list", async () => {
    serve(collection())
    const saved: unknown[] = []
    worker.use(
      http.put(`*/api/v1/collections/${ID}/glossary`, async ({ request }) => {
        saved.push(await request.json())
        return HttpResponse.json([])
      })
    )
    await open("glossary")
    await expect
      .element(
        page.getByRole("textbox", { name: "Thuật ngữ", exact: true }).first()
      )
      .toHaveValue("ADR")
    await page.getByRole("button", { name: "Thêm thuật ngữ" }).click()
    await page
      .getByRole("textbox", { name: "Thuật ngữ", exact: true })
      .nth(1)
      .fill("IV")
    await page
      .getByRole("combobox", { name: "Tên khác", exact: true })
      .nth(1)
      .fill("tiêm tĩnh mạch")
    await userEvent.keyboard("{Enter}")
    await page
      .getByRole("combobox", { name: "Tên khác", exact: true })
      .nth(1)
      .fill("truyền")
    await userEvent.keyboard("{Enter}")
    await page.getByRole("button", { name: "Lưu thuật ngữ" }).click()
    await expect.poll(() => saved).toHaveLength(1)
    expect(saved[0]).toEqual([
      {
        term: "ADR",
        case_sensitive: false,
        vietnamese_expansions: ["phản ứng có hại"],
        english_expansions: [],
        aliases: [],
        category: "",
      },
      {
        term: "IV",
        case_sensitive: false,
        vietnamese_expansions: [],
        english_expansions: [],
        aliases: ["tiêm tĩnh mạch", "truyền"],
        category: "",
      },
    ])
  })
})

describe("CollectionPage empty lists", () => {
  test("an empty glossary says so instead of showing bare buttons", async () => {
    serve(collection())
    worker.use(
      http.get(`*/api/v1/collections/${ID}/glossary`, () =>
        HttpResponse.json([])
      )
    )
    await open("glossary")
    await expect.element(page.getByText("Chưa có thuật ngữ nào.")).toBeVisible()
  })

  test("an empty colloquial list says so", async () => {
    serve(collection())
    worker.use(
      http.get(`*/api/v1/collections/${ID}/colloquial`, () =>
        HttpResponse.json([])
      ),
      http.get(`*/api/v1/collections/${ID}/sections`, () =>
        HttpResponse.json([])
      )
    )
    await open("colloquial")
    await expect
      .element(page.getByText("Chưa có tên gọi dân gian nào."))
      .toBeVisible()
  })
})

describe("CollectionPage publishing", () => {
  test("publishing shows progress until the release is ready", async () => {
    serve(collection())
    let polls = 0
    worker.use(
      http.post(`*/api/v1/collections/${ID}/publish`, () =>
        HttpResponse.json(job(), { status: 202 })
      ),
      http.get("*/api/v1/ingest-jobs/*", () => {
        polls += 1
        return HttpResponse.json(
          polls < 2
            ? job({ status: "running", step: "embed", progress: 30 })
            : job({
                status: "ready",
                step: "publish",
                progress: 100,
                release_number: 1,
              })
        )
      })
    )
    await open()
    await page.getByRole("button", { name: "Xuất bản" }).click()
    await expect.element(page.getByText("Tạo vector")).toBeVisible()
    // The job is polled every two seconds.
    await expect
      .element(page.getByText("Đã xuất bản bản 1."), { timeout: 5000 })
      .toBeVisible()
  })
})

describe("CollectionPage header", () => {
  test("a collection that cannot be loaded shows the error", async () => {
    worker.use(http.get(COLLECTION_URL, notFound))
    await open()
    await expect
      .element(page.getByText("Không tìm thấy bộ tài liệu."))
      .toBeVisible()
  })

  test("renaming saves the new title and shows it", async () => {
    serve(collection())
    const bodies: unknown[] = []
    worker.use(
      http.patch(COLLECTION_URL, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json(collection({ title: "Thuốc hô hấp" }))
      })
    )
    await open()
    await page.getByRole("button", { name: "Đổi tên" }).click()
    await page.getByLabelText("Tên bộ tài liệu").fill("Thuốc hô hấp")
    await page.getByRole("button", { name: "Lưu", exact: true }).click()
    await expect
      .element(page.getByRole("heading", { name: "Thuốc hô hấp" }))
      .toBeVisible()
    expect(bodies).toEqual([{ title: "Thuốc hô hấp" }])
  })

  test("cancelling a rename keeps the old title", async () => {
    serve(collection())
    await open()
    await page.getByRole("button", { name: "Đổi tên" }).click()
    await page.getByRole("button", { name: "Huỷ" }).click()
    await expect
      .element(page.getByRole("heading", { name: "Thuốc tim mạch" }))
      .toBeVisible()
  })

  test("changing who can see the collection saves it", async () => {
    serve(collection())
    const bodies: unknown[] = []
    worker.use(
      http.patch(COLLECTION_URL, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json(collection({ visibility: "organization" }))
      })
    )
    await open()
    await page.getByLabelText("Ai được thấy").selectOptions("organization")
    await expect.poll(() => bodies).toEqual([{ visibility: "organization" }])
    await expect
      .element(page.getByLabelText("Ai được thấy"))
      .toHaveValue("organization")
  })

  test("a refused visibility change shows the error", async () => {
    serve(collection())
    worker.use(http.patch(COLLECTION_URL, notFound))
    await open()
    await page.getByLabelText("Ai được thấy").selectOptions("organization")
    await expect
      .element(page.getByText("Không tìm thấy bộ tài liệu."))
      .toBeVisible()
  })
})

describe("CollectionPage delete", () => {
  test("deleting asks first, then returns to the collection list", async () => {
    serve(collection())
    let deleted = 0
    worker.use(
      http.delete(COLLECTION_URL, () => {
        deleted += 1
        return new HttpResponse(null, { status: 204 })
      })
    )
    await open()
    await page.getByRole("button", { name: "Xoá bộ tài liệu" }).click()
    await expect.element(page.getByText("Xoá bộ tài liệu?")).toBeVisible()
    await page.getByRole("button", { name: "Xoá", exact: true }).click()
    await expect.element(page.getByText("Danh sách bộ tài liệu")).toBeVisible()
    expect(deleted).toBe(1)
  })

  test("a refused delete shows the error and does not leave the page", async () => {
    serve(collection())
    worker.use(http.delete(COLLECTION_URL, notFound))
    await open()
    await page.getByRole("button", { name: "Xoá bộ tài liệu" }).click()
    await page.getByRole("button", { name: "Xoá", exact: true }).click()
    await expect
      .element(page.getByText("Không tìm thấy bộ tài liệu."))
      .toBeVisible()
    await expect
      .element(page.getByText("Danh sách bộ tài liệu"))
      .not.toBeInTheDocument()
  })
})

describe("CollectionPage glossary editing", () => {
  test("a removed row is left out of the saved glossary", async () => {
    serve(collection())
    const saved: unknown[] = []
    worker.use(
      http.put(`${COLLECTION_URL}/glossary`, async ({ request }) => {
        saved.push(await request.json())
        return HttpResponse.json([])
      })
    )
    await open("glossary")
    await page.getByRole("button", { name: "Xoá dòng" }).click()
    await expect.element(page.getByText("Chưa có thuật ngữ nào.")).toBeVisible()
    await page.getByRole("button", { name: "Lưu thuật ngữ" }).click()
    await expect.element(page.getByText("Đã lưu thuật ngữ.")).toBeVisible()
    expect(saved).toEqual([[]])
  })

  test("a refused glossary save shows the error", async () => {
    serve(collection())
    worker.use(http.put(`${COLLECTION_URL}/glossary`, notFound))
    await open("glossary")
    await page.getByRole("button", { name: "Lưu thuật ngữ" }).click()
    await expect
      .element(page.getByText("Không tìm thấy bộ tài liệu."))
      .toBeVisible()
  })
})
