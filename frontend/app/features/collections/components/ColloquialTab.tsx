import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import {
  getCollectionsColloquialGetQueryKey,
  useCollectionsColloquialGet,
  useCollectionsColloquialPut,
  useCollectionsSections,
} from "~/api/gen/endpoints"
import type { ColloquialMappingRecord, SectionChoice } from "~/api/gen/schemas"
import { TagsInput } from "~/components/tags-input"
import { Button } from "~/components/ui/button"
import { Input } from "~/components/ui/input"
import { Spinner } from "~/components/ui/spinner"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"

import { EmptyRows, RowListActions } from "./RowListActions"
import { SectionPicker } from "./SectionPicker"

interface Row {
  id: number
  key: string
  aliases: string[]
  visualSign: string
  products: string[]
  sections: string[]
}

const TEXT_FIELDS = ["key", "visualSign"] as const
const LIST_FIELDS = ["aliases", "products"] as const

let nextId = 0

function toRow(record: ColloquialMappingRecord): Row {
  nextId += 1
  return {
    id: nextId,
    key: record.key,
    aliases: [...(record.aliases ?? [])],
    visualSign: record.visual_sign ?? "",
    products: [...(record.product_names ?? [])],
    sections: [...(record.section_keys ?? [])],
  }
}

function toRecord(row: Row): ColloquialMappingRecord {
  return {
    key: row.key.trim(),
    aliases: row.aliases,
    visual_sign: row.visualSign.trim(),
    product_names: row.products,
    section_keys: row.sections,
  }
}

type Labels = Record<
  (typeof TEXT_FIELDS)[number] | (typeof LIST_FIELDS)[number],
  string
>

function ColloquialRow({
  row,
  choices,
  labels,
  editable,
  handlers,
}: {
  row: Row
  choices: SectionChoice[]
  labels: Labels
  editable: boolean
  handlers: { onChange: (patch: Partial<Row>) => void; onRemove: () => void }
}) {
  const { t } = useTranslation("collections")
  const { onChange, onRemove } = handlers
  return (
    <li className="grid gap-2 rounded-lg border p-3 sm:grid-cols-4">
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
      <div className="flex items-start gap-2 sm:col-span-4">
        <div className="flex-1">
          <SectionPicker
            choices={choices}
            value={row.sections}
            label={t("colloquial.sections")}
            empty={t("colloquial.noSections")}
            disabled={!editable}
            onValueChange={(sections) => onChange({ sections })}
          />
        </div>
        {editable ? (
          <Button variant="ghost" size="sm" onClick={onRemove}>
            {t("colloquial.remove")}
          </Button>
        ) : null}
      </div>
    </li>
  )
}

function ColloquialEditor({
  collectionId,
  records,
  choices,
  editable,
}: {
  collectionId: string
  records: ColloquialMappingRecord[]
  choices: SectionChoice[]
  editable: boolean
}) {
  const { t } = useTranslation("collections")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const save = useCollectionsColloquialPut()
  const [rows, setRows] = useState(() => records.map(toRow))
  const labels: Labels = {
    key: t("colloquial.key"),
    aliases: t("colloquial.aliases"),
    visualSign: t("colloquial.visualSign"),
    products: t("colloquial.products"),
  }

  function change(id: number, patch: Partial<Row>) {
    setRows((current) =>
      current.map((row) => (row.id === id ? { ...row, ...patch } : row))
    )
  }

  function remove(id: number) {
    setRows((current) => current.filter((other) => other.id !== id))
  }

  function saveAll() {
    save.mutate(
      {
        collectionId,
        data: rows.filter((row) => row.key.trim() !== "").map(toRecord),
      },
      {
        onSuccess: (saved) => {
          queryClient.setQueryData(
            getCollectionsColloquialGetQueryKey(collectionId),
            saved
          )
          toast.add({ type: "success", title: t("colloquial.saved") })
        },
        onError: (error) =>
          toast.add({ type: "error", title: apiErrorMessage(error, tErrors) }),
      }
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {rows.length === 0 ? <EmptyRows text={t("colloquial.empty")} /> : null}
      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <ColloquialRow
            key={row.id}
            row={row}
            choices={choices}
            labels={labels}
            editable={editable}
            handlers={{
              onChange: (patch) => change(row.id, patch),
              onRemove: () => remove(row.id),
            }}
          />
        ))}
      </ul>
      {editable ? (
        <RowListActions
          addLabel={t("colloquial.add")}
          saveLabel={t("colloquial.save")}
          saving={save.isPending}
          onAdd={() => setRows((current) => [...current, toRow({ key: "" })])}
          onSave={saveAll}
        />
      ) : null}
    </div>
  )
}

/** Colloquial names point to sections of this collection's documents. */
export function ColloquialTab({
  collectionId,
  editable,
}: {
  collectionId: string
  editable: boolean
}) {
  const records = useCollectionsColloquialGet(collectionId)
  const sections = useCollectionsSections(collectionId)
  if (records.data === undefined || sections.data === undefined) {
    return <Spinner />
  }
  return (
    <ColloquialEditor
      collectionId={collectionId}
      records={records.data}
      choices={sections.data}
      editable={editable}
    />
  )
}
