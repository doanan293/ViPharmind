import { HttpResponse, http } from "msw"
import { createRoutesStub } from "react-router"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { CollectionStats, Visibility } from "~/api/gen/schemas"
import { CollectionsSection } from "~/features/admin/components/CollectionsSection"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

function stats(
  title: string,
  {
    visibility = "private",
    documents = 1,
    points = 10,
    release = null,
  }: {
    visibility?: Visibility
    documents?: number
    points?: number
    release?: number | null
  } = {}
): CollectionStats {
  const id = `collection-${title}`
  return {
    collection: {
      id,
      key: title,
      title,
      visibility,
      owner_user_id: null,
      owner_organization_id: null,
      owner_name: "Khoa Dược",
      is_system: false,
      can_edit: false,
      can_set_public: false,
      current_release_id: null,
      current_release_number: release,
    },
    documents,
    qdrant_points: points,
  }
}

function CollectionStub() {
  return <p>Trang bộ tài liệu</p>
}

const Stub = createRoutesStub([
  { path: "/admin", Component: CollectionsSection },
  { path: "/collections/:id", Component: CollectionStub },
])

async function open(rows: CollectionStats[]) {
  worker.use(
    http.get("*/api/v1/admin/collections", () => HttpResponse.json(rows))
  )
  await render(
    <TestProviders>
      <Stub initialEntries={["/admin"]} />
    </TestProviders>
  )
}

/** The text of the title column, top to bottom. */
function titles(): string[] {
  return page
    .getByRole("link")
    .elements()
    .map((element) => element.textContent ?? "")
}

describe("CollectionsSection", () => {
  test("shows each collection's owner, visibility, sizes and release", async () => {
    await open([
      stats("Dược thư", {
        visibility: "public",
        documents: 1200,
        points: 34000,
        release: 3,
      }),
    ])
    await expect
      .element(page.getByRole("link", { name: "Dược thư" }))
      .toBeVisible()
    await expect.element(page.getByText("Khoa Dược")).toBeVisible()
    await expect.element(page.getByText("Công khai")).toBeVisible()
    await expect.element(page.getByText("1.200")).toBeVisible()
    await expect.element(page.getByText("34.000")).toBeVisible()
    await expect.element(page.getByText("3", { exact: true })).toBeVisible()
  })

  test("an unreleased collection shows a dash, and the title opens the collection", async () => {
    await open([stats("Phác đồ")])
    await expect.element(page.getByText("—")).toBeVisible()
    await page.getByRole("link", { name: "Phác đồ" }).click()
    await expect.element(page.getByText("Trang bộ tài liệu")).toBeVisible()
  })

  test("sorting by document count reorders the rows, largest first", async () => {
    await open([
      stats("A", { documents: 5 }),
      stats("BB", { documents: 1 }),
      stats("CCC", { documents: 9 }),
    ])
    await expect.element(page.getByRole("link", { name: "CCC" })).toBeVisible()
    const sort = page.getByRole("button", { name: "Sắp xếp theo Tài liệu" })
    await sort.click()
    await expect.poll(titles).toEqual(["CCC", "A", "BB"])
    await sort.click()
    await expect.poll(titles).toEqual(["BB", "A", "CCC"])
  })

  test("the column picker hides a column", async () => {
    await open([stats("Dược thư")])
    await expect.element(page.getByText("Khoa Dược")).toBeVisible()
    await page.getByRole("button", { name: "Cột" }).click()
    await page.getByRole("menuitemcheckbox", { name: "Chủ sở hữu" }).click()
    await expect.element(page.getByText("Khoa Dược")).not.toBeInTheDocument()
  })

  test("an empty list says there is no data", async () => {
    await open([])
    await expect.element(page.getByText("Không có dữ liệu.")).toBeVisible()
  })
})
