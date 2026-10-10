import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import {
  getUsersCurrentUserQueryKey,
  useAccountGoogleUnlink,
} from "~/api/gen/endpoints"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "~/components/ui/alert-dialog"
import { Button } from "~/components/ui/button"
import { FieldError } from "~/components/ui/field"
import { apiErrorMessage } from "~/i18n/error-message"

import { startGoogleLink } from "../lib/google-link"

export function GoogleSetting({ linked }: { linked: boolean }) {
  const { t } = useTranslation("settings")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const unlink = useAccountGoogleUnlink()
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)

  async function run(action: () => Promise<void>) {
    setError(null)
    try {
      await action()
    } catch (caught) {
      setError(apiErrorMessage(caught, tErrors))
    }
  }

  async function removeGoogle() {
    setConfirming(false)
    await run(async () => {
      const updated = await unlink.mutateAsync()
      queryClient.setQueryData(getUsersCurrentUserQueryKey(), updated)
    })
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span>
          {linked ? t("account.google.linked") : t("account.google.notLinked")}
        </span>
        <Button
          type="button"
          variant="outline"
          disabled={unlink.isPending}
          onClick={() => {
            if (linked) {
              setConfirming(true)
            } else {
              void run(startGoogleLink)
            }
          }}
        >
          {linked ? t("account.google.unlink") : t("account.google.link")}
        </Button>
      </div>
      {error === null ? null : <FieldError>{error}</FieldError>}
      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("account.google.unlinkTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("account.google.unlinkDescription")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("account.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => void removeGoogle()}
            >
              {t("account.google.unlinkConfirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
