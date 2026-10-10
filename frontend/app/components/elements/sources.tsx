import { ChevronDownIcon } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Badge } from "~/components/ui/badge"
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
  ItemMedia,
  ItemTitle,
} from "~/components/ui/item"
import { cn } from "~/lib/utils"

export interface SourceCard {
  index: number
  source: string
  title: string
  stale: boolean
}

export type SourcesProps = {
  sources: readonly SourceCard[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (index: number) => void
  className?: string
}

export function Sources({
  sources,
  open,
  onOpenChange,
  onSelect,
  className,
}: SourcesProps) {
  const { t } = useTranslation("chat")
  return (
    <Collapsible
      data-slot="sources"
      open={open}
      onOpenChange={onOpenChange}
      className={cn("w-full max-w-xl", className)}
    >
      <CollapsibleTrigger
        render={
          <Button
            variant="secondary"
            size="sm"
            className="group/trigger rounded-full"
          />
        }
      >
        {t("sources.trigger", { count: sources.length })}
        <ChevronDownIcon
          aria-hidden
          data-icon="inline-end"
          className="transition-transform group-data-panel-open/trigger:rotate-180"
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ItemGroup className="grid grid-cols-1 gap-2 pt-2 sm:grid-cols-2">
          {sources.map((source) => (
            <Item
              key={source.index}
              variant="outline"
              size="sm"
              render={(props) => <button type="button" {...props} />}
              onClick={() => onSelect(source.index)}
              className="text-start"
            >
              <ItemMedia>
                <Badge variant="secondary" className="tabular-nums">
                  {source.index}
                </Badge>
              </ItemMedia>
              <ItemContent>
                <ItemDescription className="line-clamp-1 text-xs">
                  {source.source}
                </ItemDescription>
                <ItemTitle className="line-clamp-2">{source.title}</ItemTitle>
                {source.stale ? (
                  <span className="text-xs text-amber-600 dark:text-amber-400">
                    {t("sources.stale")}
                  </span>
                ) : null}
              </ItemContent>
            </Item>
          ))}
        </ItemGroup>
      </CollapsibleContent>
    </Collapsible>
  )
}
