import { type Page, expect } from "@playwright/test"

import { type DemoContext, ask, caption, switchUser } from "../support/demo"
import { ORGANIZATION } from "./orgs"

export const COLLECTION = "Phác đồ khoa Dược"
const QUESTION =
  "Theo phác đồ của khoa, giảm đau sau mổ dùng paracetamol thế nào?"

async function pickSource(page: Page, name: string | null): Promise<void> {
  await page.getByRole("combobox", { name: /^Nguồn/ }).click()
  if (name === null) {
    await expect(page.getByRole("option", { name: COLLECTION })).toHaveCount(0)
  } else {
    await page.getByRole("option", { name }).click()
  }
  await page.keyboard.press("Escape")
}

/** Collections: an organization's protocol, published, cited for members and hidden from outsiders. */
export async function collections(page: Page, ctx: DemoContext): Promise<void> {
  if (
    ctx.owner === undefined ||
    ctx.member === undefined ||
    ctx.outsider === undefined
  ) {
    throw new Error("run auth and orgs first")
  }
  await caption(page, "Tổ chức tạo bộ tài liệu riêng: phác đồ nội bộ của khoa")
  await page.getByRole("link", { name: "Tổ chức" }).click()
  await page.getByRole("link", { name: ORGANIZATION }).click()
  await page.getByRole("tab", { name: "Bộ tài liệu" }).click()
  await page.getByLabel("Tên bộ tài liệu").fill(COLLECTION)
  await page.getByRole("button", { name: "Tạo bộ tài liệu" }).click()
  await page.getByRole("link", { name: new RegExp(COLLECTION) }).click()

  await caption(page, "Chỉ thành viên tổ chức được thấy bộ tài liệu này")
  await page.getByLabel("Ai được thấy").selectOption("organization")
  await expect(page.getByLabel("Ai được thấy")).toHaveValue("organization")

  await caption(page, "Soạn tài liệu ngay trên trình duyệt")
  await page.getByRole("link", { name: "Thêm tài liệu" }).click()
  await page.getByLabel("Tiêu đề", { exact: true }).fill("Giảm đau sau mổ")
  const content = page.getByRole("textbox", { name: "Nội dung" })
  await content.click()
  await page.keyboard.type("# Giảm đau sau mổ ở người lớn")
  await page.keyboard.press("Enter")
  await page.keyboard.type(
    "Khoa dùng paracetamol 1 g truyền tĩnh mạch mỗi 6 giờ trong 48 giờ đầu, sau đó chuyển sang uống. " +
      "Không vượt quá 3 g mỗi ngày ở người dưới 50 kg."
  )
  await page.getByRole("button", { name: "Lưu tài liệu" }).click()
  await expect(
    page.getByRole("link", { name: "Giảm đau sau mổ" })
  ).toBeVisible()

  await caption(page, "Xuất bản: tài liệu được chia đoạn và đưa vào tìm kiếm")
  await page.getByRole("button", { name: "Xuất bản" }).click()
  await expect(page.getByText(/Đã xuất bản bản \d+\./)).toBeVisible({
    timeout: 180_000,
  })

  await caption(page, "Thành viên hỏi: câu trả lời trích đúng phác đồ của khoa")
  await switchUser(page, ctx.member)
  await pickSource(page, COLLECTION)
  await ask(page, QUESTION)
  const marker = page.getByRole("button", { name: /^\d{1,3}$/ }).first()
  await marker.hover()
  await expect(page.getByText(/Giảm đau sau mổ/).last()).toBeVisible()

  await caption(
    page,
    "Người ngoài tổ chức không thấy và không được trích phác đồ này"
  )
  await switchUser(page, ctx.outsider)
  await pickSource(page, null)
  await ask(page, QUESTION)
  await expect(page.getByText(/3 g mỗi ngày ở người dưới 50 kg/)).toHaveCount(0)
}
