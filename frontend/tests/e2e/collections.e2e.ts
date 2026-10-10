import { expect, test } from "./support/fixtures"

test("an editor writes a document, publishes, and the answer cites it", async ({
  signedInPage: page,
}) => {
  await page.goto("/collections")
  await page.getByLabel("Tên bộ tài liệu").fill("Ghi chú lâm sàng E2E")
  await page.getByRole("button", { name: "Tạo bộ tài liệu" }).click()
  await expect(
    page.getByRole("heading", { name: "Ghi chú lâm sàng E2E" })
  ).toBeVisible()

  await page.getByRole("link", { name: "Thêm tài liệu" }).click()
  await page.getByLabel("Tiêu đề", { exact: true }).fill("Ibuprofen E2E")
  const content = page.getByRole("textbox", { name: "Nội dung" })
  await content.click()
  await page.keyboard.type("# Liều dùng")
  await page.keyboard.press("Enter")
  await page.keyboard.type("Người lớn uống 400 mg ibuprofen mỗi 6 giờ.")
  await page.getByRole("button", { name: "Lưu tài liệu" }).click()
  await expect(page.getByRole("link", { name: "Ibuprofen E2E" })).toBeVisible()

  await page.getByRole("button", { name: "Xuất bản" }).click()
  await expect(page.getByText("Đã xuất bản bản 1.")).toBeVisible({
    timeout: 30_000,
  })

  await page.goto("/chat")
  await page.getByRole("combobox", { name: "Nguồn" }).click()
  await page.getByRole("option", { name: "Ghi chú lâm sàng E2E" }).click()
  await page.keyboard.press("Escape")
  await expect(page.getByRole("combobox", { name: "Nguồn: 1" })).toBeVisible()
  await page
    .getByRole("textbox", { name: "Tin nhắn", exact: true })
    .fill("Người lớn uống ibuprofen bao nhiêu?")
  await page.getByRole("button", { name: "Gửi" }).click()

  const marker = page.getByRole("button", { name: "1", exact: true }).last()
  await expect(marker).toBeVisible()
  await marker.hover()
  await expect(page.getByText(/Ibuprofen E2E/).last()).toBeVisible()
})
