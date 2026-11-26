import { UploadIcon } from "lucide-react"
import { useRef, useState } from "react"
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
  const input = useRef<HTMLInputElement>(null)

  return (
    <>
      {/* The native picker shows browser chrome in the browser's language: a button opens it. */}
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={upload.isPending}
        onClick={() => input.current?.click()}
      >
        <UploadIcon aria-hidden="true" />
        {t("editor.upload")}
      </Button>
      <input
        ref={input}
        type="file"
        accept=".md,.txt,text/markdown,text/plain"
        aria-label={t("editor.upload")}
        className="sr-only"
        tabIndex={-1}
        disabled={upload.isPending}
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
