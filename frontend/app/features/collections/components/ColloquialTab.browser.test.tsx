import { HttpResponse, http } from "msw"
import { describe, expect, test } from "vitest"
import { page, userEvent } from "vitest/browser"

import type { ColloquialMappingRecord } from "~/api/gen/schemas"
import { ColloquialTab } from "~/features/collections/components/ColloquialTab"

import { renderWithProviders } from "../../../../tests/chat/render"
import { worker } from "../../../../tests/msw/browser"

const ID = "44444444-4444-4444-8444-444444444444"

const SECTIONS = [
  { key: "paracetamol/lieu-dung", label: "Paracetamol › Liều dùng" },
  { key: "paracetamol/chong-chi-dinh", label: "Paracetamol › Chống chỉ định" },
]

const HA_SOT: ColloquialMappingRecord = {
  key: "thuốc hạ sốt",
  aliases: ["thuốc giảm sốt"],
  visual_sign: "viên nén trắng",
  product_names: ["Panadol"],
  section_keys: ["paracetamol/lieu-dung"],
}

/** Serves the records and sections; returns the bodies of every PUT. */
function serve(records: ColloquialMappingRecord[]): unknown[] {
  const saved: unknown[] = []
  worker.use(
    http.get(`*/api/v1/collections/${ID}/colloquial`, () =>
      HttpResponse.json(records)
    ),
    http.get(`*/api/v1/collections/${ID}/sections`, () =>
      HttpResponse.json(SECTIONS)
    ),
    http.put(`*/api/v1/collections/${ID}/colloquial`, async ({ request }) => {
      const body = await request.json()
      saved.push(body)
      return HttpResponse.json(body)
    })
  )
  return saved
}

const keyField = () =>
  page.getByRole("textbox", { name: "Tên gọi dân gian", exact: true })

describe("ColloquialTab", () => {
  test("shows each mapping with its aliases, products and linked sections", async () => {
    serve([HA_SOT])
    await renderWithProviders(<ColloquialTab collectionId={ID} editable />)
    await expect.element(keyField()).toHaveValue("thuốc hạ sốt")
    await expect
      .element(page.getByRole("textbox", { name: "Dấu hiệu nhận biết" }))
      .toHaveValue("viên nén trắng")
    await expect.element(page.getByText("thuốc giảm sốt")).toBeVisible()
    await expect.element(page.getByText("Panadol")).toBeVisible()
    await expect
      .element(page.getByText("Paracetamol › Liều dùng"))
      .toBeVisible()
  })
})

describe("ColloquialTab saving", () => {
  test("adds a mapping linked to a section and saves the whole list, skipping blank rows", async () => {
    const saved = serve([HA_SOT])
    await renderWithProviders(<ColloquialTab collectionId={ID} editable />)
    await expect.element(keyField().first()).toHaveValue("thuốc hạ sốt")

    await page.getByRole("button", { name: "Thêm tên gọi" }).click()
    await keyField().nth(1).fill("  thuốc ho  ")
    await page
      .getByRole("combobox", { name: "Mục liên quan" })
      .nth(1)
      .fill("Chống")
    await page
      .getByRole("option", { name: "Paracetamol › Chống chỉ định" })
      .click()
    await userEvent.keyboard("{Escape}")
    // A row left blank is not sent.
    await page.getByRole("button", { name: "Thêm tên gọi" }).click()

    await page.getByRole("button", { name: "Lưu tên gọi" }).click()
    await expect.poll(() => saved).toHaveLength(1)
    expect(saved[0]).toEqual([
      {
        key: "thuốc hạ sốt",
        aliases: ["thuốc giảm sốt"],
        visual_sign: "viên nén trắng",
        product_names: ["Panadol"],
        section_keys: ["paracetamol/lieu-dung"],
      },
      {
        key: "thuốc ho",
        aliases: [],
        visual_sign: "",
        product_names: [],
        section_keys: ["paracetamol/chong-chi-dinh"],
      },
    ])
    await expect
      .element(page.getByText("Đã lưu tên gọi dân gian."))
      .toBeVisible()
  })
})

describe("ColloquialTab removing and errors", () => {
  test("removing a row leaves it out of the save", async () => {
    const saved = serve([HA_SOT])
    await renderWithProviders(<ColloquialTab collectionId={ID} editable />)
    await page.getByRole("button", { name: "Xoá dòng" }).click()
    await expect
      .element(page.getByText("Chưa có tên gọi dân gian nào."))
      .toBeVisible()
    await page.getByRole("button", { name: "Lưu tên gọi" }).click()
    await expect.poll(() => saved).toEqual([[]])
  })

  test("a failed save shows the API's error", async () => {
    serve([HA_SOT])
    worker.use(
      http.put(`*/api/v1/collections/${ID}/colloquial`, () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Not found",
            status: 404,
            code: "COLLECTION_NOT_FOUND",
          },
          {
            status: 404,
            headers: { "Content-Type": "application/problem+json" },
          }
        )
      )
    )
    await renderWithProviders(<ColloquialTab collectionId={ID} editable />)
    await page.getByRole("button", { name: "Lưu tên gọi" }).click()
    await expect
      .element(page.getByText("Không tìm thấy bộ tài liệu."))
      .toBeVisible()
  })

  test("viewers who cannot edit get read-only fields and no actions", async () => {
    serve([HA_SOT])
    await renderWithProviders(
      <ColloquialTab collectionId={ID} editable={false} />
    )
    await expect.element(keyField()).toHaveAttribute("readonly")
    await expect
      .element(page.getByRole("button", { name: "Lưu tên gọi" }))
      .not.toBeInTheDocument()
    await expect
      .element(page.getByRole("button", { name: "Xoá dòng" }))
      .not.toBeInTheDocument()
  })
})
