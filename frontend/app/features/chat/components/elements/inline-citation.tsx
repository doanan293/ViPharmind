import { Badge } from "~/components/ui/badge"
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "~/components/ui/hover-card"

export interface CitationPreview {
  source: string
  heading: string
  pages: string | null
  snippet: string
  note: string | null
}

export type CitationProps = {
  index: number
  preview: CitationPreview
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: () => void
}

export function Citation({
  index,
  preview,
  open,
  onOpenChange,
  onSelect,
}: CitationProps) {
  return (
    <HoverCard open={open} onOpenChange={onOpenChange}>
      <HoverCardTrigger
        delay={0}
        onClick={onSelect}
        render={
          <Badge
            render={(props) => <button type="button" {...props} />}
            variant={open ? "default" : "secondary"}
            className="mx-0.5 h-4 min-w-4 -translate-y-0.5 cursor-pointer px-1 align-middle text-[10px] tabular-nums"
          >
            {index}
          </Badge>
        }
      />
      <HoverCardContent side="top" sideOffset={8} className="w-72">
        <div className="flex flex-col gap-1">
          <p className="line-clamp-1 text-xs text-muted-foreground">
            {preview.source}
          </p>
          <p className="font-medium">{preview.heading}</p>
          {preview.pages === null ? null : (
            <p className="text-xs text-muted-foreground">{preview.pages}</p>
          )}
          <p className="text-muted-foreground">{preview.snippet}</p>
          {preview.note === null ? null : (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              {preview.note}
            </p>
          )}
        </div>
      </HoverCardContent>
    </HoverCard>
  )
}
