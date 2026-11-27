import { type ReactNode, useMemo } from "react"
import { useTranslation } from "react-i18next"

import { Bubble, BubbleContent } from "~/components/ui/bubble"
import { Marker, MarkerContent } from "~/components/ui/marker"
import { Message, MessageContent, MessageFooter } from "~/components/ui/message"
import {
  type MessageCitations,
  MessageCitationsProvider,
} from "~/features/chat/components/citation-context"

import type { PharmaUIMessage } from "../lib/message-schema"
import {
  describeMessage,
  type MessageNotice,
  type MessageView,
  PHASE_KEYS,
} from "../lib/message-view"

import { AnswerMarkdown } from "./AnswerMarkdown"
import { EvidencePanel } from "./EvidencePanel"
import { AgentStatus } from "./elements/agent-status"
import { ErrorState } from "./elements/error-state"
import { GuardrailNotice } from "./elements/guardrail-notice"
import { SourcesList } from "./SourcesList"

/** Props of `MessageParts`: one thread message and the session state that applies to it. */
export type MessagePartsProps = {
  message: PharmaUIMessage
  streaming: boolean
  stopped: boolean
  failed: boolean
  retrying: boolean
  onRetry: (messageId: string) => void
  onOpenCitation: (messageId: string, index: number) => void
  /** Renders the footer actions of a finished assistant answer; omitted, it has none. */
  renderActions?: (message: PharmaUIMessage, view: MessageView) => ReactNode
}

const ERROR_KEYS = {
  timeout: "error.timeout",
  network: "error.network",
  failed: "error.failed",
} as const satisfies Record<ErrorReason, string>

type ErrorReason = Extract<
  NonNullable<MessageNotice>,
  { kind: "error" }
>["reason"]

function UserMessage({ text }: { text: string }) {
  return (
    <Message align="end">
      <MessageContent>
        <Bubble variant="secondary" align="end">
          <BubbleContent className="whitespace-pre-wrap">{text}</BubbleContent>
        </Bubble>
      </MessageContent>
    </Message>
  )
}

type AnswerBodyProps = {
  view: MessageView
  streaming: boolean
  retrying: boolean
  onRetry: () => void
}

function AnswerBody({ view, streaming, retrying, onRetry }: AnswerBodyProps) {
  const { t } = useTranslation("chat")
  const { notice } = view
  if (notice?.kind === "guardrail") {
    return (
      <GuardrailNotice
        title={
          notice.reason === "blocked"
            ? t("guardrail.blocked")
            : t("guardrail.redirected")
        }
      >
        <AnswerMarkdown text={view.text} streaming={false} />
      </GuardrailNotice>
    )
  }
  if (notice?.kind === "error") {
    return (
      <>
        {view.hasText ? (
          <AnswerMarkdown text={view.text} streaming={false} />
        ) : null}
        <ErrorState
          title={t("error.title")}
          detail={t(ERROR_KEYS[notice.reason])}
          retrying={retrying}
          onRetry={onRetry}
        />
      </>
    )
  }
  return view.hasText ? (
    <AnswerMarkdown text={view.text} streaming={streaming} />
  ) : null
}

function usePhaseLabel(phase: MessageView["phase"]): string {
  const { t } = useTranslation("chat")
  if (phase === undefined) {
    return ""
  }
  return phase.phase === "searching" && typeof phase.round === "number"
    ? t("phase.searchingRound", { round: phase.round })
    : t(PHASE_KEYS[phase.phase])
}

function useCitations(
  messageId: string,
  view: MessageView,
  onOpenCitation: MessagePartsProps["onOpenCitation"]
): MessageCitations {
  return useMemo<MessageCitations>(
    () => ({
      messageId,
      sources: new Map(view.sources.map((source) => [source.index, source])),
      openCitation: (index) => onOpenCitation(messageId, index),
    }),
    [messageId, view.sources, onOpenCitation]
  )
}

/**
 * Renders one thread message: a user bubble, or an assistant answer with its agent status,
 * evidence, cited Markdown, sources, stop marker and footer actions.
 */
export function MessageParts({
  message,
  streaming,
  stopped,
  failed,
  retrying,
  onRetry,
  onOpenCitation,
  renderActions,
}: MessagePartsProps) {
  const { t } = useTranslation("chat")
  const view = useMemo(
    () => describeMessage(message, { streaming, failed }),
    [message, streaming, failed]
  )
  const citations = useCitations(message.id, view, onOpenCitation)
  const phaseLabel = usePhaseLabel(view.phase)

  if (message.role === "user") {
    return <UserMessage text={view.text} />
  }

  return (
    <Message align="start">
      <MessageContent>
        {view.showStatus ? (
          <AgentStatus state="working" label={phaseLabel} />
        ) : null}
        {view.evidence.length > 0 ? (
          <EvidencePanel
            items={view.evidence}
            searching={streaming && !view.hasText}
          />
        ) : null}
        <MessageCitationsProvider value={citations}>
          <AnswerBody
            view={view}
            streaming={streaming}
            retrying={retrying}
            onRetry={() => onRetry(message.id)}
          />
        </MessageCitationsProvider>
        {view.sources.length > 0 && view.notice === null ? (
          <SourcesList
            sources={view.sources}
            onSelect={citations.openCitation}
          />
        ) : null}
        {stopped ? (
          <Marker variant="separator">
            <MarkerContent>{t("stopped")}</MarkerContent>
          </Marker>
        ) : null}
        {renderActions !== undefined && view.canGiveFeedback ? (
          <MessageFooter>{renderActions(message, view)}</MessageFooter>
        ) : null}
      </MessageContent>
    </Message>
  )
}
