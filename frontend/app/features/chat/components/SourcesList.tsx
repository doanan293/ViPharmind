import { useMemo, useState } from "react"

import type { PharmaSourceMetadata } from "~/api/gen/schemas"

import { Sources } from "./elements/sources"

/** Props of `SourcesList`: an answer's cited sources and what selecting one does. */
export type SourcesListProps = {
  sources: readonly PharmaSourceMetadata[]
  onSelect: (index: number) => void
}

/** The collapsible source cards under an answer; selecting a card passes its citation number to `onSelect`. */
export function SourcesList({ sources, onSelect }: SourcesListProps) {
  const [open, setOpen] = useState(false)
  const cards = useMemo(
    () =>
      sources.map((source) => ({
        index: source.index,
        source: source.source,
        title: `${source.title} › ${source.section}`,
        stale: !source.isCurrent,
      })),
    [sources]
  )
  return (
    <Sources
      sources={cards}
      open={open}
      onOpenChange={setOpen}
      onSelect={onSelect}
    />
  )
}
