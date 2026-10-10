import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import {
  getCollectionsGlossaryGetQueryKey,
  useCollectionsGlossaryGet,
  useCollectionsGlossaryPut,
} from "~/api/gen/endpoints"
import type { GlossaryEntry } from "~/api/gen/schemas"
import { Button } from "~/components/ui/button"
import { Input } from "~/components/ui/input"
import { Spinner } from "~/components/ui/spinner"
import { TagsInput } from "~/components/tags-input"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"

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
  const labels = {
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

  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <li
            key={row.key}
            className="grid gap-2 rounded-lg border p-3 sm:grid-cols-5"
          >
            {TEXT_FIELDS.map((field) => (
              <Input
                key={field}
                aria-label={labels[field]}
                placeholder={labels[field]}
                value={row[field]}
                readOnly={!editable}
                onChange={(event) =>
                  change(row.key, { [field]: event.target.value })
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
                onValueChange={(value) => change(row.key, { [field]: value })}
              />
            ))}
            {editable ? (
              <Button
                variant="ghost"
                size="sm"
                className="justify-self-start"
                onClick={() =>
                  setRows((current) =>
                    current.filter((other) => other.key !== row.key)
                  )
                }
              >
                {t("glossary.remove")}
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      {editable ? (
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() =>
              setRows((current) => [...current, toRow({ term: "" })])
            }
          >
            {t("glossary.add")}
          </Button>
          <Button
            disabled={save.isPending}
            onClick={() =>
              save.mutate(
                {
                  collectionId,
                  data: rows
                    .filter((row) => row.term.trim() !== "")
                    .map(toEntry),
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
                    toast.add({
                      type: "error",
                      title: apiErrorMessage(error, tErrors),
                    }),
                }
              )
            }
          >
            {t("glossary.save")}
          </Button>
        </div>
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
