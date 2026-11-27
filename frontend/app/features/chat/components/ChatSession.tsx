import { ArrowDownIcon } from "lucide-react"
import { type ReactNode, useCallback, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import type { MessagePage } from "~/api/gen/schemas"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "~/components/ui/message-scroller"
import { CitationSheet } from "~/features/chat/components/CitationSheet"

import { useChatSession } from "../hooks/use-chat-session"
import { useContentFits } from "../hooks/use-history-sync"
import type { PharmaUIMessage } from "../lib/message-schema"
import type { MessageView } from "../lib/message-view"

import { AgentUnavailableBanner } from "./AgentUnavailableBanner"
import { Composer } from "./Composer"
import { ErrorState } from "./elements/error-state"
import { MessageActions } from "./MessageActions"
import { MessageParts } from "./MessageParts"
import { OlderMessagesLoader } from "./OlderMessagesLoader"
import { ConversationSources } from "./SourcesPopover"

/** Props of `ChatSession`: one conversation's loaded history and how to page further back. */
export type ChatSessionProps = {
  conversationId: string
  initialMessages: PharmaUIMessage[]
  pages: readonly MessagePage[]
  hasOlder: boolean
  loadingOlder: boolean
  onLoadOlder: () => void
  /** A question to send as soon as the session mounts, from the new-chat page. */
  initialQuestion: string | undefined
  onInitialQuestionSent: () => void
}

const STANDALONE_ERROR_ID = "stream-error"

type Session = ReturnType<typeof useChatSession>

type ThreadProps = {
  session: Session
  older: Pick<ChatSessionProps, "hasOlder" | "loadingOlder" | "onLoadOlder">
  renderActions: (message: PharmaUIMessage, view: MessageView) => ReactNode
}

function ThreadMessages({ session, renderActions }: ThreadProps) {
  const { t } = useTranslation("chat")
  return (
    <>
      {session.messages.map((message) => (
        <MessageScrollerItem
          key={message.id}
          messageId={message.id}
          data-message-id={message.id}
          scrollAnchor={message.role === "user"}
        >
          <MessageParts
            message={message}
            streaming={message.id === session.streamingId}
            stopped={session.stoppedIds.has(message.id)}
            failed={session.failedIds.has(message.id)}
            retrying={session.retryingId === message.id}
            onRetry={session.retry}
            onOpenCitation={session.openCitation}
            renderActions={renderActions}
          />
        </MessageScrollerItem>
      ))}
      {session.showStandaloneError ? (
        <MessageScrollerItem messageId={STANDALONE_ERROR_ID}>
          <ErrorState
            title={t("error.title")}
            detail={t("error.network")}
            retrying={false}
            onRetry={session.retryLastQuestion}
          />
        </MessageScrollerItem>
      ) : null}
    </>
  )
}

function Thread(props: ThreadProps) {
  const { t } = useTranslation("chat")
  const [userScrolled, setUserScrolled] = useState(false)
  const viewportRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const contentFits = useContentFits(viewportRef, contentRef)
  const markUserScrolled = useCallback(() => setUserScrolled(true), [])

  return (
    <MessageScrollerProvider autoScroll defaultScrollPosition="last-anchor">
      <MessageScroller className="min-h-0 flex-1">
        <OlderMessagesLoader
          {...props.older}
          userScrolled={userScrolled}
          contentFits={contentFits}
        />
        <MessageScrollerViewport
          ref={viewportRef}
          aria-label={t("thread.label")}
          onWheel={markUserScrolled}
          onTouchMove={markUserScrolled}
          onKeyDown={markUserScrolled}
        >
          <MessageScrollerContent
            ref={contentRef}
            className="mx-auto w-full max-w-3xl px-4 py-6"
          >
            <ThreadMessages {...props} />
          </MessageScrollerContent>
        </MessageScrollerViewport>
        <MessageScrollerButton direction="end">
          <ArrowDownIcon aria-hidden />
          <span className="sr-only">{t("thread.scrollToEnd")}</span>
        </MessageScrollerButton>
      </MessageScroller>
    </MessageScrollerProvider>
  )
}

/**
 * One open conversation: the message thread with infinite history upwards, the composer
 * and the citation sheet. Streams answers through the AI SDK and sends `initialQuestion`
 * once on mount.
 */
export function ChatSession({
  hasOlder,
  loadingOlder,
  onLoadOlder,
  ...options
}: ChatSessionProps) {
  const session = useChatSession(options)
  const { conversationId } = options
  const { changeFeedback, setDraft, setComposerError, ask, stop } = session

  const renderActions = useCallback(
    (message: PharmaUIMessage, view: MessageView) => (
      <MessageActions
        conversationId={conversationId}
        messageId={message.id}
        text={view.text}
        feedback={view.feedback}
        onFeedbackChange={changeFeedback}
      />
    ),
    [conversationId, changeFeedback]
  )

  return (
    <div className="flex h-full min-h-0 flex-col">
      {session.agentUnavailable ? <AgentUnavailableBanner /> : null}
      <Thread
        session={session}
        older={{ hasOlder, loadingOlder, onLoadOlder }}
        renderActions={renderActions}
      />
      <Composer
        value={session.draft}
        onValueChange={(value) => {
          setDraft(value)
          setComposerError(null)
        }}
        busy={session.busy}
        error={session.composerError}
        leading={<ConversationSources conversationId={conversationId} />}
        onSubmit={(question) => {
          setDraft("")
          ask(question)
        }}
        onStop={() => void stop()}
      />
      <CitationSheet
        target={session.citation}
        onClose={() => session.setCitation(null)}
      />
    </div>
  )
}
