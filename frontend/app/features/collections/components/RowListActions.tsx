import { Button } from "~/components/ui/button"
import { Empty, EmptyDescription, EmptyHeader } from "~/components/ui/empty"

/**
 * The add and save buttons under a list that is edited row by row and saved
 * whole, as in the glossary and colloquial tabs. Render it only for editors.
 */
export function RowListActions({
  addLabel,
  saveLabel,
  saving,
  onAdd,
  onSave,
}: {
  addLabel: string
  saveLabel: string
  saving: boolean
  onAdd: () => void
  onSave: () => void
}) {
  return (
    <div className="flex gap-2">
      <Button variant="outline" onClick={onAdd}>
        {addLabel}
      </Button>
      <Button disabled={saving} onClick={onSave}>
        {saveLabel}
      </Button>
    </div>
  )
}

/** The bordered empty state of a row-by-row list; `text` says it has no rows. */
export function EmptyRows({ text }: { text: string }) {
  return (
    <Empty className="border">
      <EmptyHeader>
        <EmptyDescription>{text}</EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}
