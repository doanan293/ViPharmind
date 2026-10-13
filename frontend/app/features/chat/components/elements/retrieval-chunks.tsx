import { ChevronDownIcon, DatabaseIcon } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "~/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "~/components/ui/collapsible"
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemHeader,
  ItemTitle,
} from "~/components/ui/item"
import { cn } from "~/lib/utils"

export interface RetrievalChunk {
  id: string
  source: string
  locator: string
  text: string
}

export type RetrievalChunksProps = {
  chunks: readonly RetrievalChunk[]
  searching: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
  className?: string
}

export function RetrievalChunks({
  chunks,
  searching,
  open,
  onOpenChange,
  className,
}: RetrievalChunksProps) {
  const { t } = useTranslation("chat")
  return (
    <Collapsible
      data-slot="retrieval-chunks"
      open={open}
      onOpenChange={onOpenChange}
      className={cn("flex w-full max-w-xl flex-col", className)}
    >
      <CollapsibleTrigger
        render={
          <Button
            variant="secondary"
            size="sm"
            className="group/trigger w-fit rounded-full"
          />
        }
      >
        <DatabaseIcon aria-hidden data-icon="inline-start" />
        {searching ? (
          <span className="shimmer motion-reduce:animate-none">
            {t("evidence.searching")}
          </span>
        ) : (
          <span>{t("evidence.read", { count: chunks.length })}</span>
        )}
        <ChevronDownIcon
          aria-hidden
          data-icon="inline-end"
          className="transition-transform group-data-panel-open/trigger:rotate-180"
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ItemGroup className="gap-1.5 pt-2">
          {chunks.map((chunk) => (
            <Item key={chunk.id} variant="outline" size="sm">
              <ItemHeader>
                <ItemTitle className="min-w-0 truncate">
                  {chunk.source}
                </ItemTitle>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {chunk.locator}
                </span>
              </ItemHeader>
              <ItemContent>
                <ItemDescription className="text-xs">
                  {chunk.text}
                </ItemDescription>
              </ItemContent>
            </Item>
          ))}
        </ItemGroup>
      </CollapsibleContent>
    </Collapsible>
  )
}
