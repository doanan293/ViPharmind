import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import {
  getCollectionsGlossaryGetQueryKey,
  useCollectionsGlossaryGet,
  useCollectionsGlossaryPut,
} from "~/api/gen/endpoints"
import type { GlossaryEntry } from "~/api/gen/schemas"
import { TagsInput } from "~/components/tags-input"
import { Button } from "~/components/ui/button"
import { Input } from "~/components/ui/input"
import { Spinner } from "~/components/ui/spinner"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"

import { EmptyRows, RowListActions } from "./RowListActions"

interface Row {
  key: number
  entry: GlossaryEntry
  term: string
  vietnamese: string[]
  english: string[]
  aliases: string[]
  category: string
}

const TEXT_FIELDS = ["term", "category"] as const
const LIST_FIELDS = ["vietnamese", "english", "aliases"] as const

let nextKey = 0

function toRow(entry: GlossaryEntry): Row {
  nextKey += 1
  return {
    key: nextKey,
    entry,
    term: entry.term,
    vietnamese: [...(entry.vietnamese_expansions ?? [])],
    english: [...(entry.english_expansions ?? [])],
    aliases: [...(entry.aliases ?? [])],
    category: entry.category ?? "",
  }
}

function toEntry(row: Row): GlossaryEntry {
  return {
    ...row.entry,
    term: row.term.trim(),
    case_sensitive: row.entry.case_sensitive ?? false,
    vietnamese_expansions: row.vietnamese,
    english_expansions: row.english,
    aliases: row.aliases,
    category: row.category.trim(),
  }
}

type Labels = Record<
  (typeof TEXT_FIELDS)[number] | (typeof LIST_FIELDS)[number],
  string
>

function GlossaryRow({
  row,
  labels,
  editable,
  onChange,
  onRemove,
}: {
  row: Row
  labels: Labels
  editable: boolean
  onChange: (patch: Partial<Row>) => void
  onRemove: () => void
}) {
  const { t } = useTranslation("collections")
  return (
    <li className="grid gap-2 rounded-lg border p-3 sm:grid-cols-5">
      {TEXT_FIELDS.map((field) => (
        <Input
          key={field}
          aria-label={labels[field]}
          placeholder={labels[field]}
          value={row[field]}
          readOnly={!editable}
          onChange={(event) => onChange({ [field]: event.target.value })}
        />
      ))}
      {LIST_FIELDS.map((field) => (
        <TagsInput
          key={field}
          label={labels[field]}
          placeholder={labels[field]}
          value={row[field]}
          disabled={!editable}
          onValueChange={(value) => onChange({ [field]: value })}
        />
      ))}
      {editable ? (
        <Button
          variant="ghost"
          size="sm"
          className="justify-self-start"
          onClick={onRemove}
        >
          {t("glossary.remove")}
        </Button>
      ) : null}
    </li>
  )
}

function GlossaryEditor({
  collectionId,
  entries,
  editable,
}: {
  collectionId: string
  entries: GlossaryEntry[]
  editable: boolean
}) {
  const { t } = useTranslation("collections")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const save = useCollectionsGlossaryPut()
  const [rows, setRows] = useState(() => entries.map(toRow))
  const labels: Labels = {
    term: t("glossary.term"),
    vietnamese: t("glossary.vietnamese"),
    english: t("glossary.english"),
    aliases: t("glossary.aliases"),
    category: t("glossary.category"),
  }

  function change(key: number, patch: Partial<Row>) {
    setRows((current) =>
      current.map((row) => (row.key === key ? { ...row, ...patch } : row))
    )
  }

  function remove(key: number) {
    setRows((current) => current.filter((other) => other.key !== key))
  }

  function saveAll() {
    save.mutate(
      {
        collectionId,
        data: rows.filter((row) => row.term.trim() !== "").map(toEntry),
      },
      {
        onSuccess: (saved) => {
          queryClient.setQueryData(
            getCollectionsGlossaryGetQueryKey(collectionId),
            saved
          )
          toast.add({ type: "success", title: t("glossary.saved") })
        },
        onError: (error) =>
          toast.add({ type: "error", title: apiErrorMessage(error, tErrors) }),
      }
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {rows.length === 0 ? <EmptyRows text={t("glossary.empty")} /> : null}
      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <GlossaryRow
            key={row.key}
            row={row}
            labels={labels}
            editable={editable}
            onChange={(patch) => change(row.key, patch)}
            onRemove={() => remove(row.key)}
          />
        ))}
      </ul>
      {editable ? (
        <RowListActions
          addLabel={t("glossary.add")}
          saveLabel={t("glossary.save")}
          saving={save.isPending}
          onAdd={() => setRows((current) => [...current, toRow({ term: "" })])}
          onSave={saveAll}
        />
      ) : null}
    </div>
  )
}

/** The glossary is edited as one list and saved whole. */
export function GlossaryTab({
  collectionId,
  editable,
}: {
  collectionId: string
  editable: boolean
}) {
  const glossary = useCollectionsGlossaryGet(collectionId)
  if (glossary.data === undefined) {
    return <Spinner />
  }
  return (
    <GlossaryEditor
      collectionId={collectionId}
      entries={glossary.data}
      editable={editable}
    />
  )
}
