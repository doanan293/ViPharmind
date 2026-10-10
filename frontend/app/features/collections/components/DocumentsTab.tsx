import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { Link } from "react-router"

import {
  getDocumentsListQueryKey,
  useDocumentsDelete,
  useDocumentsList,
} from "~/api/gen/endpoints"
import { Button, buttonVariants } from "~/components/ui/button"
import { Spinner } from "~/components/ui/spinner"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"

export function DocumentsTab({
  collectionId,
  editable,
}: {
  collectionId: string
  editable: boolean
}) {
  const { t, i18n } = useTranslation("collections")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const documents = useDocumentsList(collectionId)
  const remove = useDocumentsDelete()
  const numbers = new Intl.NumberFormat(i18n.language)
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" })

  if (documents.data === undefined) {
    return <Spinner />
  }
  return (
    <div className="flex flex-col gap-4">
      {editable ? (
        <Link
          to={`/collections/${collectionId}/documents/new`}
          className={buttonVariants({ className: "self-start" })}
        >
          {t("documents.add")}
        </Link>
      ) : null}
      {documents.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("documents.empty")}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("documents.title")}</TableHead>
              <TableHead>{t("editor.kind")}</TableHead>
              <TableHead className="text-right">
                {t("documents.chars")}
              </TableHead>
              <TableHead>{t("documents.updated")}</TableHead>
              {editable ? <TableHead /> : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {documents.data.map((document) => (
              <TableRow key={document.id}>
                <TableCell>
                  {editable ? (
                    <Link
                      to={`/collections/${collectionId}/documents/${document.id}`}
                      className="underline-offset-4 hover:underline"
                    >
                      {document.title}
                    </Link>
                  ) : (
                    document.title
                  )}
                </TableCell>
                <TableCell>{t(`editor.kindValue.${document.kind}`)}</TableCell>
                <TableCell className="text-right">
                  {numbers.format(document.char_count)}
                </TableCell>
                <TableCell>
                  {dates.format(new Date(document.updated_at))}
                </TableCell>
                {editable ? (
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={t("documents.delete", {
                        title: document.title,
                      })}
                      disabled={remove.isPending}
                      onClick={() =>
                        remove.mutate(
                          { collectionId, documentId: document.id },
                          {
                            onSuccess: () =>
                              void queryClient.invalidateQueries({
                                queryKey:
                                  getDocumentsListQueryKey(collectionId),
                              }),
                            onError: (error) =>
                              toast.add({
                                type: "error",
                                title: apiErrorMessage(error, tErrors),
                              }),
                          }
                        )
                      }
                    >
                      {t("actions.deleteConfirm")}
                    </Button>
                  </TableCell>
                ) : null}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
