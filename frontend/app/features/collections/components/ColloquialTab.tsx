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
  const labels = {
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

  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <li
            key={row.id}
            className="grid gap-2 rounded-lg border p-3 sm:grid-cols-4"
          >
            {TEXT_FIELDS.map((field) => (
              <Input
                key={field}
                aria-label={labels[field]}
                placeholder={labels[field]}
                value={row[field]}
                readOnly={!editable}
                onChange={(event) =>
                  change(row.id, { [field]: event.target.value })
                }
              />
            ))}
            {LIST_FIELDS.map((field) => (
              <TagsInput
                key={field}
                label={labels[field]}
                placeholder={labels[field]}
                value={row[field]}
                disabled={!editable}
                onValueChange={(value) => change(row.id, { [field]: value })}
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
                  onValueChange={(sections) => change(row.id, { sections })}
                />
              </div>
              {editable ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    setRows((current) =>
                      current.filter((other) => other.id !== row.id)
                    )
                  }
                >
                  {t("colloquial.remove")}
                </Button>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
      {editable ? (
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() =>
              setRows((current) => [...current, toRow({ key: "" })])
            }
          >
            {t("colloquial.add")}
          </Button>
          <Button
            disabled={save.isPending}
            onClick={() =>
              save.mutate(
                {
                  collectionId,
                  data: rows
                    .filter((row) => row.key.trim() !== "")
                    .map(toRecord),
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
                    toast.add({
                      type: "error",
                      title: apiErrorMessage(error, tErrors),
                    }),
                }
              )
            }
          >
            {t("colloquial.save")}
          </Button>
        </div>
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
