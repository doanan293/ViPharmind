import { useMemo, useState } from "react"

import type { EvidenceData } from "~/api/gen/schemas"
import { usePageText } from "~/features/chat/lib/citation-format"

import { RetrievalChunks } from "./elements/retrieval-chunks"

/** Props of `EvidencePanel`: the passages the agent read and whether it is still searching. */
export type EvidencePanelProps = {
  items: EvidenceData["items"]
  searching: boolean
}

/**
 * The collapsible list of passages the agent read for an answer. It stays open while
 * searching and closes afterwards, unless the user toggled it.
 */
export function EvidencePanel({ items, searching }: EvidencePanelProps) {
  const pageText = usePageText()
  const [openOverride, setOpenOverride] = useState<boolean | null>(null)
  const chunks = useMemo(
    () =>
      items.map((item) => ({
        id: String(item.index),
        source: `${item.title} › ${item.section}`,
        locator: pageText(item.startPage, item.endPage) ?? "",
        text: item.snippet,
      })),
    [items, pageText]
  )
  return (
    <RetrievalChunks
      chunks={chunks}
      searching={searching}
      open={openOverride ?? searching}
      onOpenChange={setOpenOverride}
    />
  )
}
