import { describe, expect, test, vi } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { ApiError } from "~/api/problem"
import { CodeStep } from "~/components/code-step"

import { TestProviders } from "../../tests/utils/providers"

async function renderStep(
  onSubmit: (code: string) => Promise<void>,
  onResend: () => Promise<void> = async () => {}
) {
  await render(
    <TestProviders>
      <CodeStep
        id="code"
        description="Đã gửi mã tới an@example.com"
        submitLabel="Xác minh"
        onSubmit={onSubmit}
        onResend={onResend}
      />
    </TestProviders>
  )
}

describe("CodeStep", () => {
  test("submits the six digits", async () => {
    const codes: string[] = []
    await renderStep(async (code) => {
      codes.push(code)
    })
    await page.getByLabelText("Mã xác minh").fill("042137")
    await page.getByRole("button", { name: "Xác minh" }).click()
    await expect.poll(() => codes).toEqual(["042137"])
  })

  test("asks for all six digits before submitting", async () => {
    await renderStep(async () => {
      throw new Error("must not submit")
    })
    await page.getByLabelText("Mã xác minh").fill("123")
    await page.getByRole("button", { name: "Xác minh" }).click()
    await expect
      .element(page.getByRole("alert"))
      .toHaveTextContent("Nhập đủ 6 chữ số.")
  })

  test("shows the server error and clears the code", async () => {
    await renderStep(async () => {
      throw new ApiError({
        status: 400,
        code: "OTP_INVALID",
        title: "Bad Request",
      })
    })
    await page.getByLabelText("Mã xác minh").fill("000000")
    await page.getByRole("button", { name: "Xác minh" }).click()
    await expect
      .element(page.getByRole("alert"))
      .toHaveTextContent("Mã không đúng hoặc đã hết hạn.")
  })

  test("resend waits for the cooldown, then follows Retry-After", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] })
    try {
      await renderStep(
        async () => {},
        async () => {
          throw new ApiError({
            status: 429,
            code: "RATE_LIMITED",
            title: "Too Many Requests",
            retryAfter: 42,
          })
        }
      )
      await expect
        .element(page.getByRole("button", { name: "Gửi lại sau 60 giây" }))
        .toBeDisabled()
      await vi.advanceTimersByTimeAsync(61_000)
      await page.getByRole("button", { name: "Gửi lại mã" }).click()
      await expect
        .element(page.getByRole("button", { name: "Gửi lại sau 42 giây" }))
        .toBeDisabled()
      await expect
        .element(page.getByRole("alert"))
        .toHaveTextContent("Bạn thao tác quá nhanh. Vui lòng thử lại sau.")
    } finally {
      vi.useRealTimers()
    }
  })
})
