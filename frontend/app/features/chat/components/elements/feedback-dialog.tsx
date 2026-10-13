import { CheckIcon, ThumbsDownIcon } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "~/components/ui/button"
import { Textarea } from "~/components/ui/textarea"
import { ToggleGroup, ToggleGroupItem } from "~/components/ui/toggle-group"
import { cn } from "~/lib/utils"

export interface FeedbackReason {
  id: string
  label: string
}

export type FeedbackDialogProps = {
  reasons: readonly FeedbackReason[]
  selected: readonly string[]
  note: string
  sent: boolean
  onToggleReason: (id: string) => void
  onNoteChange: (note: string) => void
  onSubmit: () => void
  className?: string
}

export function FeedbackDialog({
  reasons,
  selected,
  note,
  sent,
  onToggleReason,
  onNoteChange,
  onSubmit,
  className,
}: FeedbackDialogProps) {
  const { t } = useTranslation("chat")
  return (
    <div
      data-slot="feedback-dialog"
      className={cn(
        "flex w-full text-sm",
        sent ? "items-center gap-2" : "flex-col gap-3",
        className
      )}
    >
      <output className={sent ? "flex items-center gap-2" : "sr-only"}>
        {sent ? (
          <>
            <CheckIcon aria-hidden className="size-4 text-emerald-500" />
            {t("feedback.sent")}
          </>
        ) : null}
      </output>

      {sent ? null : (
        <>
          <div className="flex items-center gap-2">
            <ThumbsDownIcon
              aria-hidden
              className="size-4 text-muted-foreground"
            />
            <span className="font-medium">{t("feedback.title")}</span>
            <span className="ms-auto text-xs text-muted-foreground">
              {t("feedback.optional")}
            </span>
          </div>

          <ToggleGroup
            multiple
            variant="outline"
            size="sm"
            className="flex-wrap"
            value={[...selected]}
            onValueChange={(next) => {
              const changed = reasons.find(
                (reason) =>
                  next.includes(reason.id) !== selected.includes(reason.id)
              )?.id
              if (changed !== undefined) onToggleReason(changed)
            }}
          >
            {reasons.map((reason) => (
              <ToggleGroupItem
                key={reason.id}
                value={reason.id}
                className="rounded-full"
              >
                {reason.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>

          <Textarea
            value={note}
            onChange={(event) => onNoteChange(event.target.value)}
            rows={3}
            placeholder={t("feedback.notePlaceholder")}
            aria-label={t("feedback.notePlaceholder")}
            className="resize-none"
          />

          <Button size="sm" className="self-end" onClick={onSubmit}>
            {t("feedback.submit")}
          </Button>
        </>
      )}
    </div>
  )
}
