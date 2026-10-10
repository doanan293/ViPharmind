import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import {
  getUsersCurrentUserQueryKey,
  useAccountGoogleUnlink,
} from "~/api/gen/endpoints"
import { Button } from "~/components/ui/button"
import { apiErrorMessage } from "~/i18n/error-message"

import { startGoogleLink } from "../lib/google-link"

export function GoogleSetting({ linked }: { linked: boolean }) {
  const { t } = useTranslation("settings")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const unlink = useAccountGoogleUnlink()
  const [error, setError] = useState<string | null>(null)

  async function toggle() {
    setError(null)
    try {
      if (linked) {
        const updated = await unlink.mutateAsync()
        queryClient.setQueryData(getUsersCurrentUserQueryKey(), updated)
      } else {
        await startGoogleLink()
      }
    } catch (caught) {
      setError(apiErrorMessage(caught, tErrors))
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span>
          {linked ? t("account.google.linked") : t("account.google.notLinked")}
        </span>
        <Button type="button" variant="outline" onClick={() => void toggle()}>
          {linked ? t("account.google.unlink") : t("account.google.link")}
        </Button>
      </div>
      {error === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
