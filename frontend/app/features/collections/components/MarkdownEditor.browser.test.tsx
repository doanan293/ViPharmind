import { describe, expect, test } from "vitest"
import { page, userEvent } from "vitest/browser"
import { render } from "vitest-browser-react"

import { MarkdownEditor } from "~/features/collections/components/MarkdownEditor"

import { TestProviders } from "../../../../tests/utils/providers"

/** How long to wait for a stray `onChange` the editor might emit after mounting. */
const SETTLE_MS = 100

async function open(value = "") {
  const changes: string[] = []
  await render(
    <TestProviders>
      <span id="content-label">Nội dung</span>
      <MarkdownEditor
        labelledBy="content-label"
        value={value}
        onChange={(markdown) => changes.push(markdown)}
      />
    </TestProviders>
  )
  return changes
}

describe("MarkdownEditor", () => {
  test("typing a heading and a paragraph produces Markdown", async () => {
    const changes = await open()
    const editor = page.getByRole("textbox", { name: "Nội dung" })
    await editor.click()
    await userEvent.keyboard("# Tiêu đề{Enter}Nội dung")
    await expect.poll(() => changes.at(-1)).toBe("# Tiêu đề\n\nNội dung")
  })

  test("loads Markdown and inserts a table", async () => {
    const changes = await open("Đoạn đầu")
    const editor = page.getByRole("textbox", { name: "Nội dung" })
    await expect.element(editor).toHaveTextContent("Đoạn đầu")
    await editor.click()
    await page.getByRole("button", { name: "Chèn bảng" }).click()
    await expect.poll(() => changes.at(-1)).toContain("|")
  })

  test("opening a document does not rewrite its Markdown", async () => {
    // `*` bullets come back as `-`: the stored text must stay as written until edited.
    const changes = await open("* một\n* hai")
    await expect
      .element(page.getByRole("textbox", { name: "Nội dung" }))
      .toBeVisible()
    await new Promise((resolve) => setTimeout(resolve, SETTLE_MS))
    expect(changes).toEqual([])
  })
})

describe("MarkdownEditor toolbar", () => {
  test("formatting buttons turn the selected text into Markdown", async () => {
    const changes = await open()
    await page.getByRole("textbox", { name: "Nội dung" }).click()
    await userEvent.keyboard("Liều dùng")
    await userEvent.keyboard("{Control>}a{/Control}")
    await page.getByRole("button", { name: "Đậm" }).click()
    await expect.poll(() => changes.at(-1)).toBe("**Liều dùng**")
    await page.getByRole("button", { name: "Tiêu đề 2" }).click()
    await expect.poll(() => changes.at(-1)).toBe("## **Liều dùng**")
  })

  test("lists and italics come from their buttons", async () => {
    const changes = await open()
    await page.getByRole("textbox", { name: "Nội dung" }).click()
    await userEvent.keyboard("Uống")
    await page.getByRole("button", { name: "Danh sách", exact: true }).click()
    await expect.poll(() => changes.at(-1)).toBe("- Uống")
    await page.getByRole("button", { name: "Danh sách số" }).click()
    await expect.poll(() => changes.at(-1)).toBe("1. Uống")
    await userEvent.keyboard("{Control>}a{/Control}")
    await page.getByRole("button", { name: "Nghiêng" }).click()
    await expect.poll(() => changes.at(-1)).toBe("1. *Uống*")
  })

  test("inside a table, rows can be added and the table removed", async () => {
    const changes = await open()
    await page.getByRole("textbox", { name: "Nội dung" }).click()
    await page.getByRole("button", { name: "Chèn bảng" }).click()
    await expect.poll(() => changes.at(-1)).toContain("|")
    const rowsBefore = changes.at(-1)?.split("\n").length ?? 0
    await page.getByRole("button", { name: "Thêm hàng" }).click()
    await expect
      .poll(() => changes.at(-1)?.split("\n").length)
      .toBe(rowsBefore + 1)
    await page.getByRole("button", { name: "Xoá bảng" }).click()
    await expect.poll(() => changes.at(-1)).not.toContain("|")
    await expect
      .element(page.getByRole("button", { name: "Xoá bảng" }))
      .not.toBeInTheDocument()
  })
})
