import { useQueryClient } from "@tanstack/react-query"
import { zodResolver } from "@hookform/resolvers/zod"
import { Controller, useForm, useWatch } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { Link, useNavigate } from "react-router"
import { z } from "zod"

import {
  getDocumentsGetQueryKey,
  getDocumentsListQueryKey,
  useCollectionsGet,
  useCollectionsQuota,
  useDocumentsCreate,
  useDocumentsGet,
  useDocumentsUpdate,
} from "~/api/gen/endpoints"
import {
  type CollectionView,
  type DocumentDetail,
  type DocumentInput,
  DocumentKind,
} from "~/api/gen/schemas"
import { Button, buttonVariants } from "~/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { NativeSelect, NativeSelectOption } from "~/components/ui/native-select"
import { Spinner } from "~/components/ui/spinner"
import { toast } from "~/components/ui/toast"
import { Alert, AlertDescription } from "~/components/ui/alert"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"

import { MarkdownEditor } from "./MarkdownEditor"
import { UploadButton } from "./UploadButton"

/** The backend refuses longer documents (MAX_DOCUMENT_CHARS). */
const MAX_CHARS = 200_000

const DOCUMENT_FIELDS = [
  "title",
  "kind",
  "source_title",
  "source_url",
  "markdown",
] as const

const EMPTY: DocumentInput = {
  title: "",
  kind: "drug_monograph",
  source_title: "",
  source_url: null,
  markdown: "",
}

function inputOf(document: DocumentDetail): DocumentInput {
  return {
    title: document.title,
    kind: document.kind,
    source_title: document.source_title,
    source_url: document.source_url,
    markdown: document.markdown,
  }
}

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

type DocumentValues = {
  title: string
  kind: DocumentKind
  source_title: string
  source_url: string
  markdown: string
}

function valuesOf(input: DocumentInput): DocumentValues {
  return {
    title: input.title,
    kind: input.kind ?? "drug_monograph",
    source_title: input.source_title ?? "",
    source_url: input.source_url ?? "",
    markdown: input.markdown,
  }
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
  const { t, i18n } = useTranslation("collections")
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const create = useDocumentsCreate()
  const update = useDocumentsUpdate()
  const numbers = new Intl.NumberFormat(i18n.language)
  const collectionId = collection.id
  const schema = z.object({
    title: z.string().trim().min(1, t("editor.titleRequired")).max(200),
    kind: z.enum(DocumentKind),
    source_title: z.string().trim().max(500),
    source_url: z.union([
      z.literal(""),
      z.url(t("editor.invalidUrl")).max(2000),
    ]),
    markdown: z
      .string()
      .refine((text) => text.trim() !== "", t("editor.contentRequired"))
      .refine((text) => text.length <= MAX_CHARS, {
        message: t("editor.tooLong", { max: numbers.format(MAX_CHARS) }),
      }),
  })
  const form = useForm<DocumentValues>({
    resolver: zodResolver(schema),
    defaultValues: valuesOf(initial),
  })
  const markdown = useWatch({ control: form.control, name: "markdown" })
  const title = useWatch({ control: form.control, name: "title" })
  const chars = markdown.length
  const serverError = form.formState.errors.root?.server?.message

  async function onSubmit(values: DocumentValues) {
    const data: DocumentInput = {
      ...values,
      source_url: values.source_url === "" ? null : values.source_url,
    }
    try {
      if (documentId === null) {
        await create.mutateAsync({ collectionId, data })
      } else {
        await update.mutateAsync({ collectionId, documentId, data })
        await queryClient.invalidateQueries({
          queryKey: getDocumentsGetQueryKey(collectionId, documentId),
        })
      }
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

  return (
    <form
      noValidate
      onSubmit={form.handleSubmit(onSubmit)}
      className="flex flex-col gap-4"
    >
      <FieldGroup className="grid gap-4 sm:grid-cols-2">
        <Controller
          name="title"
          control={form.control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor="document-title">
                {t("editor.title")}
              </FieldLabel>
              <Input
                {...field}
                id="document-title"
                maxLength={200}
                aria-invalid={fieldState.invalid}
              />
              <FieldError errors={[fieldState.error]} />
            </Field>
          )}
        />
        <Controller
          name="kind"
          control={form.control}
          render={({ field }) => (
            <Field>
              <FieldLabel htmlFor="document-kind">
                {t("editor.kind")}
              </FieldLabel>
              <NativeSelect
                id="document-kind"
                value={field.value}
                onBlur={field.onBlur}
                onChange={(event) => {
                  const kind = Object.values(DocumentKind).find(
                    (value) => value === event.target.value
                  )
                  if (kind !== undefined) field.onChange(kind)
                }}
              >
                {Object.values(DocumentKind).map((kind) => (
                  <NativeSelectOption key={kind} value={kind}>
                    {t(`editor.kindValue.${kind}`)}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
          )}
        />
        <Controller
          name="source_title"
          control={form.control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor="document-source">
                {t("editor.source")}
              </FieldLabel>
              <Input
                {...field}
                id="document-source"
                maxLength={500}
                aria-invalid={fieldState.invalid}
              />
              <FieldError errors={[fieldState.error]} />
            </Field>
          )}
        />
        <Controller
          name="source_url"
          control={form.control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor="document-source-url">
                {t("editor.sourceUrl")}
              </FieldLabel>
              <Input
                {...field}
                id="document-source-url"
                type="url"
                aria-invalid={fieldState.invalid}
              />
              <FieldError errors={[fieldState.error]} />
            </Field>
          )}
        />
      </FieldGroup>
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
                collectionId={collectionId}
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
            <FieldDescription
              className={chars > MAX_CHARS ? "text-destructive" : undefined}
            >
              {t("editor.chars", {
                count: numbers.format(chars),
                max: numbers.format(MAX_CHARS),
              })}
            </FieldDescription>
            <FieldError errors={[fieldState.error]} />
            <TextQuota collection={collection} />
          </Field>
        )}
      />
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
          initial={EMPTY}
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
