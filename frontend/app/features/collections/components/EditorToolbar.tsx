import type { Editor } from "@tiptap/react"
import {
  BetweenHorizontalEndIcon,
  BoldIcon,
  Heading1Icon,
  Heading2Icon,
  Heading3Icon,
  ItalicIcon,
  ListIcon,
  ListOrderedIcon,
  TableIcon,
  Trash2Icon,
} from "lucide-react"
import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "~/components/ui/button"
import { ButtonGroup } from "~/components/ui/button-group"
import { Separator } from "~/components/ui/separator"
import { Toggle } from "~/components/ui/toggle"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "~/components/ui/tooltip"

interface Mark {
  label: string
  icon: ReactNode
  active: boolean
  run: () => void
}

/** Heading levels the toolbar offers, with their icons. */
const HEADINGS = [
  { level: 1, Icon: Heading1Icon },
  { level: 2, Icon: Heading2Icon },
  { level: 3, Icon: Heading3Icon },
] as const

/** Rows and columns of a newly inserted table. */
const NEW_TABLE_SIZE = 3

function MarkToggles({ editor }: { editor: Editor }) {
  const { t } = useTranslation("collections", { keyPrefix: "editor.toolbar" })
  const chain = () => editor.chain().focus()
  const marks: Mark[] = [
    ...HEADINGS.map(({ level, Icon }) => ({
      label: t(`h${level}`),
      icon: <Icon />,
      active: editor.isActive("heading", { level }),
      run: () => chain().toggleHeading({ level }).run(),
    })),
    {
      label: t("bold"),
      icon: <BoldIcon />,
      active: editor.isActive("bold"),
      run: () => chain().toggleBold().run(),
    },
    {
      label: t("italic"),
      icon: <ItalicIcon />,
      active: editor.isActive("italic"),
      run: () => chain().toggleItalic().run(),
    },
    {
      label: t("bullet"),
      icon: <ListIcon />,
      active: editor.isActive("bulletList"),
      run: () => chain().toggleBulletList().run(),
    },
    {
      label: t("ordered"),
      icon: <ListOrderedIcon />,
      active: editor.isActive("orderedList"),
      run: () => chain().toggleOrderedList().run(),
    },
  ]
  return marks.map((mark) => (
    <Tooltip key={mark.label}>
      <TooltipTrigger
        render={
          <Toggle
            size="sm"
            aria-label={mark.label}
            pressed={mark.active}
            onPressedChange={mark.run}
          />
        }
      >
        {mark.icon}
      </TooltipTrigger>
      <TooltipContent>{mark.label}</TooltipContent>
    </Tooltip>
  ))
}

function TableActions({ editor }: { editor: Editor }) {
  const { t } = useTranslation("collections", { keyPrefix: "editor.toolbar" })
  const chain = () => editor.chain().focus()
  const actions = [
    {
      label: t("table"),
      icon: <TableIcon />,
      run: () =>
        chain()
          .insertTable({
            rows: NEW_TABLE_SIZE,
            cols: NEW_TABLE_SIZE,
            withHeaderRow: true,
          })
          .run(),
    },
    ...(editor.isActive("table")
      ? [
          {
            label: t("addRow"),
            icon: <BetweenHorizontalEndIcon />,
            run: () => chain().addRowAfter().run(),
          },
          {
            label: t("deleteTable"),
            icon: <Trash2Icon />,
            run: () => chain().deleteTable().run(),
          },
        ]
      : []),
  ]
  return (
    <ButtonGroup>
      {actions.map((action) => (
        <Tooltip key={action.label}>
          <TooltipTrigger
            render={
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={action.label}
                onClick={action.run}
              />
            }
          >
            {action.icon}
          </TooltipTrigger>
          <TooltipContent>{action.label}</TooltipContent>
        </Tooltip>
      ))}
    </ButtonGroup>
  )
}

/** Formatting the corpus understands: headings split sections, tables stay tables. */
export function EditorToolbar({ editor }: { editor: Editor }) {
  return (
    <div
      role="toolbar"
      className="flex flex-wrap items-center gap-1 border-b bg-muted/40 p-1"
    >
      <MarkToggles editor={editor} />
      <Separator orientation="vertical" className="mx-1 h-5" />
      <TableActions editor={editor} />
    </div>
  )
}
