import type { Editor } from "@tiptap/react"
import { useTranslation } from "react-i18next"

import { Button } from "~/components/ui/button"

interface Action {
  label: string
  active?: boolean
  run: () => void
}

/** Formatting the corpus understands: headings split sections, tables stay tables. */
export function EditorToolbar({ editor }: { editor: Editor }) {
  const { t } = useTranslation("collections", { keyPrefix: "editor.toolbar" })
  const chain = () => editor.chain().focus()
  const inTable = editor.isActive("table")
  const actions: Action[] = [
    ...([1, 2, 3] as const).map((level) => ({
      label: t(`h${level}`),
      active: editor.isActive("heading", { level }),
      run: () => chain().toggleHeading({ level }).run(),
    })),
    {
      label: t("bold"),
      active: editor.isActive("bold"),
      run: () => chain().toggleBold().run(),
    },
    {
      label: t("italic"),
      active: editor.isActive("italic"),
      run: () => chain().toggleItalic().run(),
    },
    {
      label: t("bullet"),
      active: editor.isActive("bulletList"),
      run: () => chain().toggleBulletList().run(),
    },
    {
      label: t("ordered"),
      active: editor.isActive("orderedList"),
      run: () => chain().toggleOrderedList().run(),
    },
    {
      label: t("table"),
      run: () =>
        chain().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(),
    },
    ...(inTable
      ? [
          { label: t("addRow"), run: () => chain().addRowAfter().run() },
          { label: t("deleteTable"), run: () => chain().deleteTable().run() },
        ]
      : []),
  ]
  return (
    <div
      role="toolbar"
      className="flex flex-wrap gap-1 border-b bg-muted/40 p-1"
    >
      {actions.map((action) => (
        <Button
          key={action.label}
          type="button"
          size="sm"
          variant={action.active === true ? "secondary" : "ghost"}
          aria-pressed={action.active}
          onClick={action.run}
        >
          {action.label}
        </Button>
      ))}
    </div>
  )
}
