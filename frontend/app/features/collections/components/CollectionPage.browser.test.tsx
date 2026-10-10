import { http, HttpResponse } from "msw"
import { createRoutesStub } from "react-router"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { CollectionView, JobView } from "~/api/gen/schemas"
import { Toaster } from "~/components/ui/toast"
import { CollectionPage } from "~/features/collections/components/CollectionPage"

import { worker } from "../../../../tests/msw/browser"
import { accountView } from "../../../../tests/utils/account"
import { TestProviders } from "../../../../tests/utils/providers"

const ID = "44444444-4444-4444-8444-444444444444"

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

async function open(tab = "documents") {
  const Stub = createRoutesStub([
    {
      path: "/collections/:collectionId/:tab?",
      Component: () => <CollectionPage collectionId={ID} tab={tab} />,
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

describe("CollectionPage", () => {
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
      .getByRole("textbox", { name: "Tên khác", exact: true })
      .nth(1)
      .fill("tiêm tĩnh mạch, truyền")
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
