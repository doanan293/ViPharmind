import { HttpResponse, http } from "msw"
import { createRoutesStub, useParams } from "react-router"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { CollectionGroups, CollectionView } from "~/api/gen/schemas"
import { CollectionsPage } from "~/features/collections/components/CollectionsPage"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const ORG = "11111111-1111-4111-8111-111111111111"
const CREATED = "66666666-6666-4666-8666-666666666666"

function collection(
  id: string,
  title: string,
  overrides: Partial<CollectionView> = {}
): CollectionView {
  return {
    id,
    key: id,
    title,
    visibility: "private",
    owner_user_id: null,
    owner_organization_id: null,
    owner_name: "An",
    is_system: false,
    can_edit: true,
    can_set_public: false,
    current_release_id: null,
    current_release_number: null,
    ...overrides,
  }
}

const EMPTY: CollectionGroups = {
  mine: [],
  organizations: [],
  public: [],
  others: [],
}

/** The page a link or a created collection opens: shows the collection id. */
function CollectionStub() {
  const { collectionId } = useParams()
  return <p>Bộ tài liệu {collectionId}</p>
}

async function open(
  groups: CollectionGroups,
  quota = {
    text_used: 1500,
    text_limit: 10000,
    collections_used: 1,
    collections_limit: 5,
  }
) {
  worker.use(
    http.get("*/api/v1/collections", () => HttpResponse.json(groups)),
    http.get("*/api/v1/collections/quota", () => HttpResponse.json(quota))
  )
  const Stub = createRoutesStub([
    { path: "/collections", Component: CollectionsPage },
    { path: "/collections/:collectionId", Component: CollectionStub },
  ])
  await render(
    <TestProviders>
      <Stub initialEntries={["/collections"]} />
    </TestProviders>
  )
}

describe("CollectionsPage", () => {
  test("groups collections by owner and marks the system corpus", async () => {
    await open({
      mine: [collection("m1", "Ghi chú của tôi")],
      organizations: [
        {
          organization_id: ORG,
          name: "Khoa Dược",
          role: "editor",
          items: [
            collection("o1", "Phác đồ khoa", { visibility: "organization" }),
          ],
        },
      ],
      public: [
        collection("p1", "Dược thư Quốc gia", {
          visibility: "public",
          is_system: true,
        }),
      ],
      others: [],
    })
    await expect
      .element(page.getByRole("heading", { name: "Của tôi" }))
      .toBeVisible()
    await expect
      .element(page.getByRole("heading", { name: "Khoa Dược" }))
      .toBeVisible()
    await expect
      .element(page.getByRole("heading", { name: "Công khai" }))
      .toBeVisible()
    await expect
      .element(page.getByRole("heading", { name: "Khác (quản trị)" }))
      .not.toBeInTheDocument()
    await expect.element(page.getByText("Hệ thống")).toBeVisible()
    await expect.element(page.getByText("Cả tổ chức")).toBeVisible()
    await expect
      .element(page.getByText("Chưa có bộ tài liệu nào."))
      .not.toBeInTheDocument()

    await page.getByRole("link", { name: /Phác đồ khoa/ }).click()
    await expect.element(page.getByText("Bộ tài liệu o1")).toBeVisible()
  })

  test("shows the quota used and an empty state", async () => {
    await open(EMPTY)
    await expect
      .element(page.getByText("Chưa có bộ tài liệu nào."))
      .toBeVisible()
    const quota = "Đã dùng 1.500 / 10.000 ký tự · 1 / 5 bộ tài liệu"
    await expect.element(page.getByText(quota)).toBeVisible()
    await expect
      .element(page.getByRole("progressbar", { name: quota }))
      .toHaveAttribute("aria-valuenow", "15")
  })
})

describe("CollectionsPage quota and creation", () => {
  test("a zero text quota shows a full bar", async () => {
    await open(EMPTY, {
      text_used: 0,
      text_limit: 0,
      collections_used: 0,
      collections_limit: 0,
    })
    await expect
      .element(page.getByRole("progressbar"))
      .toHaveAttribute("aria-valuenow", "100")
  })

  test("creating a collection opens it", async () => {
    const created: unknown[] = []
    worker.use(
      http.post("*/api/v1/collections", async ({ request }) => {
        created.push(await request.json())
        return HttpResponse.json(collection(CREATED, "Thuốc kháng sinh"), {
          status: 201,
        })
      })
    )
    await open(EMPTY)
    await page.getByLabelText("Tên bộ tài liệu").fill("Thuốc kháng sinh")
    await page.getByRole("button", { name: "Tạo bộ tài liệu" }).click()
    await expect.poll(() => created).toEqual([{ title: "Thuốc kháng sinh" }])
    await expect.element(page.getByText(`Bộ tài liệu ${CREATED}`)).toBeVisible()
  })
})
