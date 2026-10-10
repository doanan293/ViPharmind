import type { Editor } from "@tiptap/react"
import {
  BoldIcon,
  Heading1Icon,
  Heading2Icon,
  Heading3Icon,
  ItalicIcon,
  ListIcon,
  ListOrderedIcon,
  TableIcon,
  Trash2Icon,
  BetweenHorizontalEndIcon,
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

/** Formatting the corpus understands: headings split sections, tables stay tables. */
export function EditorToolbar({ editor }: { editor: Editor }) {
  const { t } = useTranslation("collections", { keyPrefix: "editor.toolbar" })
  const chain = () => editor.chain().focus()
  const headingIcons = [Heading1Icon, Heading2Icon, Heading3Icon]
  const marks: Mark[] = [
    ...([1, 2, 3] as const).map((level) => {
      const Icon = headingIcons[level - 1]
      return {
        label: t(`h${level}`),
        icon: Icon === undefined ? null : <Icon />,
        active: editor.isActive("heading", { level }),
        run: () => chain().toggleHeading({ level }).run(),
      }
    }),
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
  const tableActions = [
    {
      label: t("table"),
      icon: <TableIcon />,
      run: () =>
        chain().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(),
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
    <div
      role="toolbar"
      className="flex flex-wrap items-center gap-1 border-b bg-muted/40 p-1"
    >
      {marks.map((mark) => (
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
      ))}
      <Separator orientation="vertical" className="mx-1 h-5" />
      <ButtonGroup>
        {tableActions.map((action) => (
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
    </div>
  )
}
