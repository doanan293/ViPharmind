import { useState } from "react"
import { useTranslation } from "react-i18next"

import { useDocumentsUpload } from "~/api/gen/endpoints"
import type { UploadResult } from "~/api/gen/schemas"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "~/components/ui/alert-dialog"
import { Button } from "~/components/ui/button"
import { Input } from "~/components/ui/input"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"

/** Turns a .md or .txt file into a title and Markdown; asks before replacing typed content. */
export function UploadButton({
  collectionId,
  hasContent,
  onLoaded,
}: {
  collectionId: string
  hasContent: boolean
  onLoaded: (result: UploadResult) => void
}) {
  const { t } = useTranslation("collections")
  const { t: tErrors } = useTranslation("errors")
  const upload = useDocumentsUpload()
  const [pending, setPending] = useState<UploadResult | null>(null)

  return (
    <>
      <Input
        type="file"
        accept=".md,.txt,text/markdown,text/plain"
        aria-label={t("editor.upload")}
        title={t("editor.upload")}
        disabled={upload.isPending}
        className="max-w-xs"
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ""
          if (file === undefined) return
          upload.mutate(
            { collectionId, data: { file } },
            {
              onSuccess: (result) =>
                hasContent ? setPending(result) : onLoaded(result),
              onError: (error) =>
                toast.add({
                  type: "error",
                  title: apiErrorMessage(error, tErrors),
                }),
            }
          )
        }}
      />
      <AlertDialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPending(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("editor.replace")}</AlertDialogTitle>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("actions.cancel")}</AlertDialogCancel>
            <Button
              onClick={() => {
                if (pending !== null) onLoaded(pending)
                setPending(null)
              }}
            >
              {t("actions.save")}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
