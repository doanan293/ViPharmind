import { useCallback, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { useLocation, useNavigate } from "react-router"

import { Button } from "~/components/ui/button"
import {
  Empty,
  EmptyContent,
  EmptyHeader,
  EmptyTitle,
} from "~/components/ui/empty"
import { Spinner } from "~/components/ui/spinner"

import { useMessageHistory } from "../hooks/use-message-history"
import { toPharmaMessage } from "../lib/chat-messages"
import { readInitialQuestion } from "../lib/location-state"

import { ChatSession } from "./ChatSession"
import { NewChat } from "./NewChat"

/** Props of `ChatThread`; an undefined id means a new chat. */
export type ChatThreadProps = {
  conversationId: string | undefined
}

/** The loading state of the chat page, also used as its route Suspense fallback. */
export function ChatThreadFallback() {
  const { t } = useTranslation("chat")
  return (
    <output className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
      <Spinner />
      {t("thread.loading")}
    </output>
  )
}

function ConversationChat({ conversationId }: { conversationId: string }) {
  const { t } = useTranslation("chat")
  const navigate = useNavigate()
  const location = useLocation()
  const initialQuestion = readInitialQuestion(location.state)
  const { history, notFound } = useMessageHistory(conversationId)
  const {
    data,
    isError,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
    refetch,
  } = history
  const firstPage = data?.pages[0]
  const initialMessages = useMemo(
    () => firstPage?.items.map(toPharmaMessage) ?? [],
    [firstPage]
  )

  const clearInitialQuestion = useCallback(() => {
    void navigate(location.pathname, { replace: true, state: null })
  }, [navigate, location.pathname])

  const loadOlder = useCallback(() => {
    void fetchNextPage()
  }, [fetchNextPage])

  if (isError && data === undefined) {
    if (notFound) {
      return null
    }
    return (
      <Empty className="h-full">
        <EmptyHeader>
          <EmptyTitle>{t("thread.loadFailed")}</EmptyTitle>
        </EmptyHeader>
        <EmptyContent>
          <Button variant="outline" onClick={() => void refetch()}>
            {t("thread.reload")}
          </Button>
        </EmptyContent>
      </Empty>
    )
  }

  if (data === undefined || firstPage === undefined) {
    return <ChatThreadFallback />
  }

  return (
    <ChatSession
      conversationId={conversationId}
      initialMessages={initialMessages}
      pages={data.pages}
      hasOlder={hasNextPage}
      loadingOlder={isFetchingNextPage}
      onLoadOlder={loadOlder}
      initialQuestion={initialQuestion}
      onInitialQuestionSent={clearInitialQuestion}
    />
  )
}

/**
 * The chat page body: the new-chat screen without a conversation id, otherwise the
 * conversation's history and session. Remounts when the conversation changes.
 */
export function ChatThread({ conversationId }: ChatThreadProps) {
  if (conversationId === undefined) {
    return <NewChat />
  }
  return (
    <ConversationChat key={conversationId} conversationId={conversationId} />
  )
}
