import { CheckIcon } from "lucide-react"
import type { ComponentProps } from "react"
import { useTranslation } from "react-i18next"

import { Badge } from "~/components/ui/badge"
import { Spinner } from "~/components/ui/spinner"

/** What the agent is doing, which picks the status icon and the screen reader text. */
export type AgentState = "working" | "waiting" | "done"

/** Props of `AgentStatus`; other props go to the `<output>` element. */
export type AgentStatusProps = Omit<ComponentProps<"output">, "children"> & {
  state: AgentState
  label: string
  elapsed?: string
}

/** A live status badge with the agent's current step, announced to screen readers through `<output>`. */
export function AgentStatus({
  state,
  label,
  elapsed,
  ...props
}: AgentStatusProps) {
  const { t } = useTranslation("chat")
  return (
    <output data-slot="agent-status" {...props}>
      <Badge variant="outline" className="h-6 gap-1.5 px-2.5 font-normal">
        {state === "done" ? (
          <CheckIcon aria-hidden data-icon="inline-start" />
        ) : (
          <Spinner data-icon="inline-start" />
        )}
        <span className="sr-only">
          {state === "done" ? t("status.done") : t("status.working")}
        </span>
        <span className="max-w-72 truncate">{label}</span>
        {elapsed !== undefined && state !== "done" ? (
          <span className="text-muted-foreground tabular-nums">{elapsed}</span>
        ) : null}
      </Badge>
    </output>
  )
}
