import { expect, type Page } from "@playwright/test"

import { caption, type DemoContext } from "../support/demo"

export async function intro(page: Page, _ctx: DemoContext): Promise<void> {
  await page.goto("/")
  await expect(page).toHaveTitle(/^ViPharmind/)
  await caption(page, "ViPharmind: trợ lý tra cứu thuốc cho người Việt")
}
