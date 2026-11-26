import { type Page, expect } from "@playwright/test"

import { type DemoContext, ask, caption, logIn } from "../support/demo"

/** Drug Q&A: streamed answer with steps and citations, a follow-up, an off-topic question, feedback. */
export async function chat(page: Page, ctx: DemoContext): Promise<void> {
  if (ctx.owner !== undefined && !page.url().includes("/chat"))
    await logIn(page, ctx.owner)
  await page.goto("/chat")
  await caption(
    page,
    "Hỏi về thuốc bằng tiếng Việt: agent tìm trong Dược thư và tờ hướng dẫn sử dụng"
  )
  await ask(page, "Paracetamol người lớn uống tối đa bao nhiêu một ngày?")

  await caption(page, "Mỗi ý có trích dẫn [1], [2]: rê chuột để xem đoạn nguồn")
  const marker = page.getByRole("button", { name: "1", exact: true }).last()
  await marker.hover()
  await expect(page.getByText(/^Trích từ mục /)).toBeVisible()
  await page.waitForTimeout(1_500)
  await caption(page, "Bấm vào trích dẫn để mở nguyên văn đoạn tài liệu")
  await marker.click()
  await expect(page.getByRole("heading", { name: "Nguồn [1]" })).toBeVisible()
  await page.waitForTimeout(2_500)
  await page.keyboard.press("Escape")

  await caption(page, "Câu hỏi nối tiếp hiểu ngữ cảnh của câu trước")
  await ask(page, "Còn trẻ em thì sao?")

  await caption(page, "Câu hỏi ngoài phạm vi thuốc được từ chối lịch sự")
  await ask(page, "Viết giúp tôi một bài thơ về mùa thu")

  await caption(page, "Đánh giá câu trả lời để nhóm phát triển cải thiện")
  await page
    .getByRole("button", { name: "Hữu ích", exact: true })
    .first()
    .click()
  await page.waitForTimeout(1_500)
}
