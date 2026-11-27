import { CircleAlertIcon, RefreshCwIcon } from "lucide-react"
import { useTranslation } from "react-i18next"

import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import { Spinner } from "~/components/ui/spinner"
import { cn } from "~/lib/utils"

/** Props of `ErrorState`: the translated message and the retry action. */
export type ErrorStateProps = {
  title: string
  detail: string
  retrying: boolean
  onRetry: () => void
  className?: string
}

/** An error alert for a failed answer with a retry button; while `retrying` it shows a spinner and a retrying label instead. */
export function ErrorState({
  title,
  detail,
  retrying,
  onRetry,
  className,
}: ErrorStateProps) {
  const { t } = useTranslation("chat")
  if (retrying) {
    return (
      <output
        data-slot="error-state"
        className={cn(
          "flex w-full max-w-xl items-center gap-2 text-sm text-muted-foreground",
          className
        )}
      >
        <Spinner />
        <span className="shimmer motion-reduce:animate-none">
          {t("error.retrying")}
        </span>
      </output>
    )
  }

  return (
    <Alert
      data-slot="error-state"
      variant="destructive"
      className={cn("max-w-xl", className)}
    >
      <CircleAlertIcon aria-hidden />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{detail}</AlertDescription>
      <AlertAction>
        <Button variant="ghost" size="sm" onClick={onRetry}>
          <RefreshCwIcon aria-hidden data-icon="inline-start" />
          {t("error.retry")}
        </Button>
      </AlertAction>
    </Alert>
  )
}
