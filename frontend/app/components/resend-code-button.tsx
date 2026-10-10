import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { isApiError } from "~/api/problem"
import { Button } from "~/components/ui/button"
import { useCountdown } from "~/hooks/use-countdown"
import { apiErrorMessage } from "~/i18n/error-message"

function isRateLimited(error: unknown): boolean {
  return isApiError(error) && error.retryAfter !== undefined
}

/** The backend's minimum gap between two codes to the same address. */
export const RESEND_COOLDOWN_SECONDS = 60

export function ResendCodeButton({
  onResend,
  sendError = null,
}: {
  onResend: () => Promise<void>
  /** Why the code asked for before this button appeared was not sent, if it was not. */
  sendError?: unknown
}) {
  const { t } = useTranslation("common")
  const { t: tErrors } = useTranslation("errors")
  const { secondsLeft, start } = useCountdown()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(() =>
    sendError === null || isRateLimited(sendError)
      ? null
      : apiErrorMessage(sendError, tErrors)
  )

  useEffect(() => {
    if (sendError === null) {
      start(RESEND_COOLDOWN_SECONDS)
    } else if (isApiError(sendError) && sendError.retryAfter !== undefined) {
      // An earlier code is still on its way; wait as long as the server asks.
      start(sendError.retryAfter)
    }
  }, [sendError, start])

  async function resend() {
    setPending(true)
    setError(null)
    try {
      await onResend()
      start(RESEND_COOLDOWN_SECONDS)
    } catch (caught) {
      if (isApiError(caught) && caught.retryAfter !== undefined) {
        start(caught.retryAfter)
      }
      setError(apiErrorMessage(caught, tErrors))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex flex-col items-start gap-1 text-sm">
      <Button
        type="button"
        variant="link"
        className="h-auto p-0"
        disabled={pending || secondsLeft > 0}
        onClick={() => void resend()}
      >
        {secondsLeft > 0
          ? t("code.resendIn", { seconds: secondsLeft })
          : t("code.resend")}
      </Button>
      {error === null ? null : (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
