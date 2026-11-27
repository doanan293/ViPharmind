import { HttpResponse, http } from "msw"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import type { ReleaseView } from "~/api/gen/schemas"
import { Toaster } from "~/components/ui/toast"
import { ReleasesTab } from "~/features/collections/components/ReleasesTab"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const ID = "44444444-4444-4444-8444-444444444444"
const RELEASES = `*/api/v1/collections/${ID}/releases`
const ROLLBACK = `*/api/v1/collections/${ID}/rollback`
const HTTP_CONFLICT = 409
const FIRST = 1
const SECOND = 2

function release(number: number, overrides: Partial<ReleaseView> = {}) {
  return {
    id: `r${number}`,
    number,
    status: "retired",
    current: false,
    created_at: "2026-10-11T09:00:00Z",
    published_at: "2026-10-11T09:05:00Z",
    ...overrides,
  } satisfies ReleaseView
}

const CURRENT = release(SECOND, { status: "ready", current: true })

/** Serves `releases` and renders the tab; returns how many times the list was fetched. */
async function open(releases: ReleaseView[], editable = true) {
  const fetches = { count: 0 }
  worker.use(
    http.get(RELEASES, () => {
      fetches.count += 1
      return HttpResponse.json(releases)
    })
  )
  await render(
    <TestProviders>
      <Toaster>
        <ReleasesTab collectionId={ID} editable={editable} />
      </Toaster>
    </TestProviders>
  )
  return fetches
}

describe("ReleasesTab", () => {
  test("lists releases and marks the current one", async () => {
    await open([CURRENT, release(FIRST, { published_at: null })])
    await expect.element(page.getByText(/Bản 2/)).toBeVisible()
    await expect.element(page.getByText("Đang dùng")).toBeVisible()
    await expect.element(page.getByText("Bản 1")).toBeVisible()
  })

  test("viewers and a collection without an older release cannot roll back", async () => {
    await open([CURRENT, release(FIRST)], false)
    await expect.element(page.getByText("Bản 1")).toBeVisible()
    await expect
      .element(page.getByRole("button", { name: "Quay lại bản trước" }))
      .not.toBeInTheDocument()
  })

  test("rolling back announces the restored release and reloads the list", async () => {
    let calls = 0
    worker.use(
      http.post(ROLLBACK, () => {
        calls += 1
        return HttpResponse.json(release(FIRST, { current: true }))
      })
    )
    const fetches = await open([CURRENT, release(FIRST)])
    await page.getByRole("button", { name: "Quay lại bản trước" }).click()
    await expect.element(page.getByText("Đã quay lại bản 1.")).toBeVisible()
    expect(calls).toBe(1)
    await expect.poll(() => fetches.count).toBe(2)
  })

  test("a refused roll-back shows the error", async () => {
    worker.use(
      http.post(ROLLBACK, () =>
        HttpResponse.json(
          {
            type: "urn:pharma-agent:problem:collection-not-found",
            title: "Not found",
            status: HTTP_CONFLICT,
            code: "COLLECTION_NOT_FOUND",
          },
          {
            status: HTTP_CONFLICT,
            headers: { "Content-Type": "application/problem+json" },
          }
        )
      )
    )
    await open([CURRENT, release(FIRST)])
    await page.getByRole("button", { name: "Quay lại bản trước" }).click()
    await expect
      .element(page.getByText("Không tìm thấy bộ tài liệu."))
      .toBeVisible()
  })
})
