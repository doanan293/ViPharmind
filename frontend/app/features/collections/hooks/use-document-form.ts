import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

import {
  getDocumentsGetQueryKey,
  getDocumentsListQueryKey,
  useDocumentsCreate,
  useDocumentsUpdate,
} from "~/api/gen/endpoints"
import type { DocumentInput } from "~/api/gen/schemas"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"

import {
  DOCUMENT_FIELDS,
  type DocumentValues,
  documentSchema,
  inputFromValues,
  MAX_DOCUMENT_CHARS,
  valuesOf,
} from "../lib/document-form"

/** What {@link useDocumentForm} edits: `documentId` null creates a document. */
export type DocumentFormOptions = {
  collectionId: string
  documentId: string | null
  initial: DocumentInput
}

/**
 * The document editor's form state and submit handler. A successful save
 * refreshes the cached document list, shows a toast and returns to the list;
 * API errors land on the matching field or the form's `root.server` error.
 */
export function useDocumentForm({
  collectionId,
  documentId,
  initial,
}: DocumentFormOptions) {
  const { t, i18n } = useTranslation("collections")
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const create = useDocumentsCreate()
  const update = useDocumentsUpdate()
  const numbers = new Intl.NumberFormat(i18n.language)
  const schema = documentSchema({
    titleRequired: t("editor.titleRequired"),
    invalidUrl: t("editor.invalidUrl"),
    contentRequired: t("editor.contentRequired"),
    tooLong: t("editor.tooLong", {
      max: numbers.format(MAX_DOCUMENT_CHARS),
    }),
  })
  const form = useForm<DocumentValues>({
    resolver: zodResolver(schema),
    defaultValues: valuesOf(initial),
  })

  async function persist(data: DocumentInput) {
    if (documentId === null) {
      await create.mutateAsync({ collectionId, data })
      return
    }
    await update.mutateAsync({ collectionId, documentId, data })
    await queryClient.invalidateQueries({
      queryKey: getDocumentsGetQueryKey(collectionId, documentId),
    })
  }

  async function onSubmit(values: DocumentValues) {
    try {
      await persist(inputFromValues(values))
    } catch (error) {
      applyApiError(
        error,
        form.setError,
        DOCUMENT_FIELDS,
        apiErrorMessage(error, tErrors)
      )
      return
    }
    await queryClient.invalidateQueries({
      queryKey: getDocumentsListQueryKey(collectionId),
    })
    toast.add({ type: "success", title: t("editor.saved") })
    await navigate(`/collections/${collectionId}/documents`)
  }

  return { form, onSubmit }
}
