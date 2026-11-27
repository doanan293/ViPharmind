import { Controller, type UseFormReturn, useWatch } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { Link } from "react-router"

import {
  useCollectionsGet,
  useCollectionsQuota,
  useDocumentsGet,
} from "~/api/gen/endpoints"
import type { CollectionView, DocumentInput } from "~/api/gen/schemas"
import { Alert, AlertDescription } from "~/components/ui/alert"
import { Button, buttonVariants } from "~/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
} from "~/components/ui/field"
import { Spinner } from "~/components/ui/spinner"
import { apiErrorMessage } from "~/i18n/error-message"

import { useDocumentForm } from "../hooks/use-document-form"
import {
  type DocumentValues,
  EMPTY_DOCUMENT,
  inputOf,
  MAX_DOCUMENT_CHARS,
} from "../lib/document-form"
import { DocumentMetaFields } from "./DocumentFields"
import { MarkdownEditor } from "./MarkdownEditor"
import { UploadButton } from "./UploadButton"

function TextQuota({ collection }: { collection: CollectionView }) {
  const { t, i18n } = useTranslation("collections")
  const quota = useCollectionsQuota(
    collection.owner_organization_id === null
      ? undefined
      : { organization_id: collection.owner_organization_id }
  )
  if (quota.data === undefined) return null
  const numbers = new Intl.NumberFormat(i18n.language)
  return (
    <p className="text-sm text-muted-foreground">
      {t("list.quota", {
        used: numbers.format(quota.data.text_used),
        limit: numbers.format(quota.data.text_limit),
        count: quota.data.collections_used,
        max: quota.data.collections_limit,
      })}
    </p>
  )
}

function CharCount({ chars }: { chars: number }) {
  const { t, i18n } = useTranslation("collections")
  const numbers = new Intl.NumberFormat(i18n.language)
  return (
    <FieldDescription
      className={chars > MAX_DOCUMENT_CHARS ? "text-destructive" : undefined}
    >
      {t("editor.chars", {
        count: numbers.format(chars),
        max: numbers.format(MAX_DOCUMENT_CHARS),
      })}
    </FieldDescription>
  )
}

function ContentField({
  collection,
  form,
}: {
  collection: CollectionView
  form: UseFormReturn<DocumentValues>
}) {
  const { t } = useTranslation("collections")
  const markdown = useWatch({ control: form.control, name: "markdown" })
  const title = useWatch({ control: form.control, name: "title" })
  return (
    <Controller
      name="markdown"
      control={form.control}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span id="document-content-label" className="text-sm font-medium">
              {t("editor.content")}
            </span>
            <UploadButton
              collectionId={collection.id}
              hasContent={title !== "" || markdown !== ""}
              onLoaded={(result) => {
                form.setValue("title", result.title, { shouldDirty: true })
                field.onChange(result.markdown)
              }}
            />
          </div>
          <MarkdownEditor
            labelledBy="document-content-label"
            value={field.value}
            onChange={field.onChange}
          />
          <CharCount chars={markdown.length} />
          <FieldError errors={[fieldState.error]} />
          <TextQuota collection={collection} />
        </Field>
      )}
    />
  )
}

function DocumentForm({
  collection,
  documentId,
  initial,
}: {
  collection: CollectionView
  documentId: string | null
  initial: DocumentInput
}) {
  const { t } = useTranslation("collections")
  const collectionId = collection.id
  const { form, onSubmit } = useDocumentForm({
    collectionId,
    documentId,
    initial,
  })
  const serverError = form.formState.errors.root?.server?.message

  return (
    <form
      noValidate
      onSubmit={form.handleSubmit(onSubmit)}
      className="flex flex-col gap-4"
    >
      <FieldGroup className="grid gap-4 sm:grid-cols-2">
        <DocumentMetaFields control={form.control} />
      </FieldGroup>
      <ContentField collection={collection} form={form} />
      {serverError === undefined ? null : (
        <FieldError>{serverError}</FieldError>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? <Spinner /> : null}
          {t("editor.save")}
        </Button>
        <Link
          to={`/collections/${collectionId}/documents`}
          className={buttonVariants({ variant: "outline" })}
        >
          {t("editor.back")}
        </Link>
      </div>
    </form>
  )
}

function ExistingDocument({
  collection,
  documentId,
}: {
  collection: CollectionView
  documentId: string
}) {
  const { t: tErrors } = useTranslation("errors")
  const document = useDocumentsGet(collection.id, documentId)
  if (document.isError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          {apiErrorMessage(document.error, tErrors)}
        </AlertDescription>
      </Alert>
    )
  }
  if (document.data === undefined) return <Spinner />
  return (
    <DocumentForm
      collection={collection}
      documentId={documentId}
      initial={inputOf(document.data)}
    />
  )
}

/** Write a document in the editor or fill it from a file; `documentId` "new" creates one. */
export function DocumentEditorPage({
  collectionId,
  documentId,
}: {
  collectionId: string
  documentId: string
}) {
  const { t } = useTranslation("collections")
  const { t: tErrors } = useTranslation("errors")
  const collection = useCollectionsGet(collectionId)

  if (collection.isError) {
    return (
      <Alert variant="destructive" className="m-4 w-auto md:m-8">
        <AlertDescription>
          {apiErrorMessage(collection.error, tErrors)}
        </AlertDescription>
      </Alert>
    )
  }
  if (collection.data === undefined) return <Spinner />
  const creating = documentId === "new"
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 p-4 md:p-8">
      <title>{creating ? t("editor.newTitle") : collection.data.title}</title>
      <div className="flex flex-col gap-1">
        <p className="text-sm text-muted-foreground">{collection.data.title}</p>
        <h1 className="text-2xl font-semibold">
          {creating ? t("editor.newTitle") : t("editor.title")}
        </h1>
      </div>
      {creating ? (
        <DocumentForm
          collection={collection.data}
          documentId={null}
          initial={EMPTY_DOCUMENT}
        />
      ) : (
        <ExistingDocument
          collection={collection.data}
          documentId={documentId}
        />
      )}
    </div>
  )
}
