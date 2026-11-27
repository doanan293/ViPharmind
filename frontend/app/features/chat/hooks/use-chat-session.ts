import { useCallback, useRef, useState } from "react"

import type { MessageFeedback, MessagePage } from "~/api/gen/schemas"

import type { CitationTarget } from "../components/CitationSheet"
import {
  dropTrailingTurn,
  questionBefore,
  textOf,
  withFeedback,
} from "../lib/chat-messages"
import type { PharmaUIMessage } from "../lib/message-schema"
import { readStreamProblem } from "../lib/stream-problem"
import {
  usePrependOlderPages,
  useSendInitialQuestion,
} from "./use-history-sync"
import { usePharmaChat } from "./use-pharma-chat"
import { useStreamProblemHandler } from "./use-stream-problem-handler"

/** Inputs of `useChatSession`: the conversation, its loaded history and the opening question. */
export type ChatSessionOptions = {
  conversationId: string
  initialMessages: PharmaUIMessage[]
  pages: readonly MessagePage[]
  initialQuestion: string | undefined
  onInitialQuestionSent: () => void
}

function useComposerState() {
  const [draft, setDraft] = useState("")
  const [composerError, setComposerError] = useState<string | null>(null)
  const [agentUnavailable, setAgentUnavailable] = useState(false)
  const lastQuestionRef = useRef("")
  const restoreDraft = useCallback(() => setDraft(lastQuestionRef.current), [])
  return {
    draft,
    setDraft,
    composerError,
    setComposerError,
    agentUnavailable,
    setAgentUnavailable,
    lastQuestionRef,
    restoreDraft,
  }
}

type Chat = ReturnType<typeof usePharmaChat>

function useRetryActions(chat: Chat, ask: (question: string) => void) {
  const { messages, failedIds, setMessages, setRetryingId } = chat
  const retry = useCallback(
    (messageId: string) => {
      const question = questionBefore(messages, messageId)
      if (question === undefined) {
        return
      }
      setRetryingId(messageId)
      if (failedIds.has(messageId) && messages.at(-1)?.id === messageId) {
        setMessages(dropTrailingTurn(messages))
      }
      ask(question)
    },
    [messages, failedIds, setMessages, setRetryingId, ask]
  )
  const retryLastQuestion = useCallback(() => {
    const last = messages.at(-1)
    if (last?.role !== "user") {
      return
    }
    setMessages(messages.slice(0, -1))
    ask(textOf(last))
  }, [messages, setMessages, ask])
  return { retry, retryLastQuestion }
}

function useThreadStatus(chat: Chat) {
  const { messages, status, error } = chat
  const busy = status === "submitted" || status === "streaming"
  const lastMessage = messages.at(-1)
  const streamProblem = error === undefined ? null : readStreamProblem(error)
  return {
    busy,
    streamingId:
      busy && lastMessage?.role === "assistant" ? lastMessage.id : undefined,
    showStandaloneError:
      status === "error" &&
      streamProblem === null &&
      lastMessage?.role === "user",
  }
}

/**
 * State and actions of one open conversation: the AI SDK chat, the composer draft and its
 * error, retries, feedback, the open citation and loading older history. `ChatSession`
 * renders what it returns.
 */
export function useChatSession(options: ChatSessionOptions) {
  const composer = useComposerState()
  const handleProblem = useStreamProblemHandler(composer)
  const chat = usePharmaChat({
    conversationId: options.conversationId,
    initialMessages: options.initialMessages,
    onProblem: handleProblem,
  })
  const [citation, setCitation] = useState<CitationTarget | null>(null)
  const { sendMessage, setMessages } = chat
  const { lastQuestionRef, setComposerError, setAgentUnavailable } = composer

  const ask = useCallback(
    (question: string) => {
      lastQuestionRef.current = question
      setComposerError(null)
      setAgentUnavailable(false)
      void sendMessage({ text: question })
    },
    [sendMessage, lastQuestionRef, setComposerError, setAgentUnavailable]
  )
  const changeFeedback = useCallback(
    (messageId: string, feedback: MessageFeedback | null) => {
      setMessages((current) => withFeedback(current, messageId, feedback))
    },
    [setMessages]
  )
  const openCitation = useCallback((messageId: string, index: number) => {
    setCitation({ messageId, index })
  }, [])

  const retryActions = useRetryActions(chat, ask)
  const threadStatus = useThreadStatus(chat)
  usePrependOlderPages(options.pages, setMessages)
  useSendInitialQuestion({
    initialQuestion: options.initialQuestion,
    sendMessage,
    lastQuestionRef,
    onSent: options.onInitialQuestionSent,
  })

  return {
    ...composer,
    ...chat,
    ...retryActions,
    ...threadStatus,
    ask,
    changeFeedback,
    citation,
    setCitation,
    openCitation,
  }
}
