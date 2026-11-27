import { HttpResponse, http } from "msw"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, test } from "vitest"
import { page, userEvent } from "vitest/browser"

import type { ConversationView } from "~/api/gen/schemas"
import {
  Sidebar,
  SidebarContent,
  SidebarProvider,
} from "~/components/ui/sidebar"
import { TooltipProvider } from "~/components/ui/tooltip"

import {
  conversationPage,
  conversationView,
} from "../../../../tests/chat/fixtures"
import { renderRoutes } from "../../../../tests/chat/render"
import { worker } from "../../../../tests/msw/browser"

import { ConversationSidebar } from "./ConversationSidebar"

/** A desktop-sized viewport for every sidebar test. */
const DESKTOP_WIDTH = 1280
const DESKTOP_HEIGHT = 800

/** The sidebar's page size, and how many conversations the paging test serves. */
const PAGE_SIZE = 20
const TOTAL = 25

/** A list short enough to fit on one page. */
const SHORT_LIST = 3

async function setDesktopViewport() {
  await page.viewport(DESKTOP_WIDTH, DESKTOP_HEIGHT)
}

function SidebarWrap({ children }: { children: ReactNode }) {
  return (
    <TooltipProvider>
      <SidebarProvider>
        <Sidebar collapsible="none" className="h-[400px]">
          <SidebarContent>{children}</SidebarContent>
        </Sidebar>
      </SidebarProvider>
    </TooltipProvider>
  )
}

function conversations(from: number, to: number): ConversationView[] {
  return Array.from({ length: to - from + 1 }, (_unused, offset) => {
    const number = from + offset
    return conversationView(`c${number}`, `Hội thoại ${number}`)
  })
}

type ListPage = {
  cursor: string | null
  items: ConversationView[]
  next: string | null
}

function listHandler(pages: readonly ListPage[]) {
  return http.get("*/api/v1/conversations", ({ request }) => {
    const cursor = new URL(request.url).searchParams.get("cursor")
    const match = pages.find((candidate) => candidate.cursor === cursor)
    return HttpResponse.json(
      conversationPage(match?.items ?? [], match?.next ?? null)
    )
  })
}

describe("ConversationSidebar", () => {
  beforeEach(setDesktopViewport)

  test("marks the active conversation and loads the next page at the end of the list", async () => {
    worker.use(
      listHandler([
        { cursor: null, items: conversations(1, PAGE_SIZE), next: "cursor-2" },
        {
          cursor: "cursor-2",
          items: conversations(PAGE_SIZE + 1, TOTAL),
          next: null,
        },
      ])
    )
    await renderRoutes(ConversationSidebar, {
      initialEntry: "/chat/c2",
      wrap: SidebarWrap,
    })
    await expect
      .element(page.getByRole("link", { name: "Hội thoại 2", exact: true }))
      .toHaveAttribute("aria-current", "page")
    page
      .getByRole("link", { name: "Hội thoại 20", exact: true })
      .element()
      .scrollIntoView()
    await expect
      .element(page.getByRole("link", { name: "Hội thoại 25", exact: true }))
      .toBeInTheDocument()
  })

  test("shows the empty state", async () => {
    worker.use(listHandler([{ cursor: null, items: [], next: null }]))
    await renderRoutes(ConversationSidebar, {
      initialEntry: "/chat",
      wrap: SidebarWrap,
    })
    await expect
      .element(page.getByText("Chưa có cuộc trò chuyện nào"))
      .toBeVisible()
  })
})

describe("ConversationSidebar rename", () => {
  beforeEach(setDesktopViewport)

  test("renames a conversation", async () => {
    worker.use(
      listHandler([
        { cursor: null, items: conversations(1, SHORT_LIST), next: null },
      ])
    )
    const patched: unknown[] = []
    worker.use(
      http.patch(
        "*/api/v1/conversations/:conversationId",
        async ({ request, params }) => {
          patched.push(await request.json())
          return HttpResponse.json(
            conversationView(String(params.conversationId), "Liều paracetamol")
          )
        }
      )
    )
    await renderRoutes(ConversationSidebar, {
      initialEntry: "/chat",
      wrap: SidebarWrap,
    })
    await page.getByRole("button", { name: "Thao tác với Hội thoại 1" }).click()
    await page.getByRole("menuitem", { name: "Đổi tên" }).click()
    const title = page.getByRole("textbox", { name: "Tên" })
    await expect.element(title).toHaveValue("Hội thoại 1")
    await userEvent.fill(title, "Liều paracetamol")
    await page.getByRole("button", { name: "Lưu" }).click()
    await expect
      .element(page.getByRole("link", { name: "Liều paracetamol" }))
      .toBeVisible()
    expect(patched).toEqual([{ title: "Liều paracetamol" }])
  })
})

describe("ConversationSidebar delete", () => {
  beforeEach(setDesktopViewport)

  test("deletes the active conversation and returns to /chat", async () => {
    worker.use(
      listHandler([
        { cursor: null, items: conversations(1, SHORT_LIST), next: null },
      ])
    )
    const deleted: string[] = []
    worker.use(
      http.delete("*/api/v1/conversations/:conversationId", ({ params }) => {
        deleted.push(String(params.conversationId))
        return new HttpResponse(null, { status: 204 })
      })
    )
    await renderRoutes(ConversationSidebar, {
      initialEntry: "/chat/c2",
      wrap: SidebarWrap,
    })
    await page.getByRole("button", { name: "Thao tác với Hội thoại 2" }).click()
    await page.getByRole("menuitem", { name: "Xoá" }).click()
    await expect
      .element(
        page.getByText("“Hội thoại 2” và toàn bộ tin nhắn sẽ bị xoá vĩnh viễn.")
      )
      .toBeVisible()
    await page
      .getByRole("alertdialog")
      .getByRole("button", { name: "Xoá" })
      .click()
    await expect
      .element(page.getByRole("link", { name: "Hội thoại 2", exact: true }))
      .not.toBeInTheDocument()
    await expect
      .element(page.getByTestId("location"))
      .toMatchTextContent(/^\/chat$/)
    expect(deleted).toEqual(["c2"])
  })
})
