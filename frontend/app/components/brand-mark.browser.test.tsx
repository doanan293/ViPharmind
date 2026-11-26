import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { BrandMark } from "~/components/brand-mark"

import { TestProviders } from "../../tests/utils/providers"

describe("BrandMark", () => {
  test("shows the logo and the product name; the logo is then decorative", async () => {
    await render(
      <TestProviders>
        <BrandMark />
      </TestProviders>
    )
    await expect.element(page.getByText("ViPharmind")).toBeVisible()
    await expect
      .element(page.getByRole("img", { name: "ViPharmind" }))
      .not.toBeInTheDocument()
  })

  test("the logo alone carries the name for screen readers", async () => {
    await render(
      <TestProviders>
        <BrandMark withName={false} />
      </TestProviders>
    )
    await expect
      .element(page.getByRole("img", { name: "ViPharmind" }))
      .toBeVisible()
  })
})
