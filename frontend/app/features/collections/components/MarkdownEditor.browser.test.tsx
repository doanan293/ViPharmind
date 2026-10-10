import { describe, expect, test } from "vitest"
import { page, userEvent } from "vitest/browser"
import { render } from "vitest-browser-react"

import { MarkdownEditor } from "~/features/collections/components/MarkdownEditor"

import { TestProviders } from "../../../../tests/utils/providers"

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
})
