import { ShieldIcon } from "lucide-react"
import type { ReactNode } from "react"

import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { cn } from "~/lib/utils"

/** Props of `GuardrailNotice`: its translated title and the explanation to show under it. */
export type GuardrailNoticeProps = {
  title: string
  children: ReactNode
  className?: string
}

/** The notice that replaces an answer when the guardrail blocked or redirected the question. */
export function GuardrailNotice({
  title,
  children,
  className,
}: GuardrailNoticeProps) {
  return (
    <Alert
      data-slot="guardrail-notice"
      role="note"
      className={cn("max-w-xl", className)}
    >
      <ShieldIcon aria-hidden />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  )
}
