import { useQueryClient } from "@tanstack/react-query"
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link, useNavigate } from "react-router"

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
import { Field, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { NativeSelect, NativeSelectOption } from "~/components/ui/native-select"
import { Spinner } from "~/components/ui/spinner"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"

import { MarkdownEditor } from "./MarkdownEditor"
import { UploadButton } from "./UploadButton"

/** The backend refuses longer documents (MAX_DOCUMENT_CHARS). */
const MAX_CHARS = 200_000

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
  const [form, setForm] = useState(initial)
  const numbers = new Intl.NumberFormat(i18n.language)
  const chars = form.markdown.length
  const collectionId = collection.id
  const pending = create.isPending || update.isPending
  const set = (patch: Partial<DocumentInput>) =>
    setForm((current) => ({ ...current, ...patch }))

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data: DocumentInput = {
      title: form.title.trim(),
      kind: form.kind,
      source_title: (form.source_title ?? "").trim(),
      source_url: form.source_url?.trim() || null,
      markdown: form.markdown,
    }
    const done = {
      onSuccess: () => {
        void queryClient.invalidateQueries({
          queryKey: getDocumentsListQueryKey(collectionId),
        })
        if (documentId !== null) {
          void queryClient.invalidateQueries({
            queryKey: getDocumentsGetQueryKey(collectionId, documentId),
          })
        }
        toast.add({ type: "success", title: t("editor.saved") })
        void navigate(`/collections/${collectionId}/documents`)
      },
      onError: (error: unknown) =>
        toast.add({ type: "error", title: apiErrorMessage(error, tErrors) }),
    }
    if (documentId === null) {
      create.mutate({ collectionId, data }, done)
    } else {
      update.mutate({ collectionId, documentId, data }, done)
    }
  }

  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field>
          <FieldLabel htmlFor="document-title">{t("editor.title")}</FieldLabel>
          <Input
            id="document-title"
            value={form.title}
            maxLength={200}
            required
            onChange={(event) => set({ title: event.target.value })}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="document-kind">{t("editor.kind")}</FieldLabel>
          <NativeSelect
            id="document-kind"
            value={form.kind}
            onChange={(event) => {
              const kind = Object.values(DocumentKind).find(
                (value) => value === event.target.value
              )
              if (kind !== undefined) set({ kind })
            }}
          >
            {Object.values(DocumentKind).map((kind) => (
              <NativeSelectOption key={kind} value={kind}>
                {t(`editor.kindValue.${kind}`)}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Field>
        <Field>
          <FieldLabel htmlFor="document-source">
            {t("editor.source")}
          </FieldLabel>
          <Input
            id="document-source"
            value={form.source_title ?? ""}
            maxLength={500}
            onChange={(event) => set({ source_title: event.target.value })}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="document-source-url">
            {t("editor.sourceUrl")}
          </FieldLabel>
          <Input
            id="document-source-url"
            type="url"
            value={form.source_url ?? ""}
            onChange={(event) => set({ source_url: event.target.value })}
          />
        </Field>
      </div>
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span id="document-content-label" className="text-sm font-medium">
            {t("editor.content")}
          </span>
          <UploadButton
            collectionId={collectionId}
            hasContent={form.title !== "" || form.markdown !== ""}
            onLoaded={(result) =>
              set({ title: result.title, markdown: result.markdown })
            }
          />
        </div>
        <MarkdownEditor
          labelledBy="document-content-label"
          value={form.markdown}
          onChange={(markdown) => set({ markdown })}
        />
        <span
          className={
            chars > MAX_CHARS
              ? "text-sm text-destructive"
              : "text-sm text-muted-foreground"
          }
        >
          {t("editor.chars", {
            count: numbers.format(chars),
            max: numbers.format(MAX_CHARS),
          })}
        </span>
        <TextQuota collection={collection} />
      </div>
      <div className="flex gap-2">
        <Button
          type="submit"
          disabled={
            pending ||
            form.title.trim() === "" ||
            form.markdown.trim() === "" ||
            chars > MAX_CHARS
          }
        >
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
      <p role="alert" className="text-sm text-destructive">
        {apiErrorMessage(document.error, tErrors)}
      </p>
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
      <p role="alert" className="p-8 text-sm text-destructive">
        {apiErrorMessage(collection.error, tErrors)}
      </p>
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
