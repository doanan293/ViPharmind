import { useChat } from "@ai-sdk/react"
import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import type { ApiError } from "~/api/problem"
import { toast } from "~/components/ui/toast"
import {
  invalidateConversations,
  updateConversationTitle,
} from "~/features/conversations/lib/conversation-cache"

import { dropTrailingTurn } from "../lib/chat-messages"
import { createChatTransport } from "../lib/chat-transport"
import {
  messageMetadataSchema,
  type PharmaUIMessage,
  pharmaDataPartSchemas,
} from "../lib/message-schema"
import { readStreamProblem } from "../lib/stream-problem"

/** Inputs of `usePharmaChat`. */
export type PharmaChatOptions = {
  conversationId: string
  initialMessages: PharmaUIMessage[]
  /**
   * Called with the problem+json error of a failed stream, after the failed turn has been
   * dropped from the thread. Streams that fail without a problem body never reach it.
   */
  onProblem: (problem: ApiError) => void
}

function withId(ids: ReadonlySet<string>, id: string): ReadonlySet<string> {
  const next = new Set(ids)
  next.add(id)
  return next
}

function useMessageFlags() {
  const [stoppedIds, setStoppedIds] = useState<ReadonlySet<string>>(
    () => new Set()
  )
  const [failedIds, setFailedIds] = useState<ReadonlySet<string>>(
    () => new Set()
  )
  const [retryingId, setRetryingId] = useState<string | null>(null)
  return {
    stoppedIds,
    failedIds,
    retryingId,
    setRetryingId,
    markStopped: (id: string) =>
      setStoppedIds((current) => withId(current, id)),
    markFailed: (id: string) => setFailedIds((current) => withId(current, id)),
  }
}

/**
 * The AI SDK chat of one conversation, wired to the Pharma stream transport and the
 * conversations cache. Besides the `useChat` result it tracks which answers were stopped,
 * which failed, and which one is being retried.
 */
export function usePharmaChat({
  conversationId,
  initialMessages,
  onProblem,
}: PharmaChatOptions) {
  const { t } = useTranslation("chat")
  const queryClient = useQueryClient()
  const [transport] = useState(createChatTransport)
  const flags = useMessageFlags()

  const chat = useChat<PharmaUIMessage>({
    id: conversationId,
    messages: initialMessages,
    transport,
    dataPartSchemas: pharmaDataPartSchemas,
    messageMetadataSchema,
    onData: (part) => {
      if (
        part.type === "data-conversation" &&
        !updateConversationTitle(queryClient, part.data)
      ) {
        void invalidateConversations(queryClient)
      }
    },
    onFinish: ({ message, isAbort, isError, isDisconnect }) => {
      flags.setRetryingId(null)
      if (isAbort) {
        flags.markStopped(message.id)
      }
      if (isError || isDisconnect) {
        flags.markFailed(message.id)
      }
      if (message.metadata?.persisted === false) {
        toast.add({ title: t("notPersisted"), type: "warning" })
      }
      void invalidateConversations(queryClient)
    },
    onError: (streamError) => {
      const problem = readStreamProblem(streamError)
      if (problem !== null) {
        chat.setMessages((current) => dropTrailingTurn(current))
        onProblem(problem)
      }
    },
  })

  return { ...chat, ...flags }
}
