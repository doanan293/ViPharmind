import type {
  UIMessage as ApiUIMessage,
  MessageFeedback,
  MessagePage,
} from "~/api/gen/schemas"

import type { PharmaMessagePart, PharmaUIMessage } from "./message-schema"

/** Converts a stored message from the history API into the AI SDK message shape the thread renders. */
export function toPharmaMessage(message: ApiUIMessage): PharmaUIMessage {
  return {
    id: message.id,
    role: message.role,
    metadata: message.metadata,
    parts: message.parts.map((part): PharmaMessagePart => {
      if (part.type === "text") {
        return { type: "text", text: part.text }
      }
      return {
        type: "source-document",
        sourceId: part.sourceId,
        mediaType: part.mediaType,
        title: part.title,
        providerMetadata: { pharma: { ...part.providerMetadata.pharma } },
      }
    }),
  }
}

/** Puts older history before the current messages, skipping any message the thread already has. */
export function prependOlder(
  current: readonly PharmaUIMessage[],
  older: readonly PharmaUIMessage[]
): PharmaUIMessage[] {
  const known = new Set(current.map((message) => message.id))
  return [...older.filter((message) => !known.has(message.id)), ...current]
}

/**
 * The messages of the history pages after the first `appliedPageCount`, oldest first. Pages
 * come newest first from the API, so they are reversed.
 */
export function olderMessagesFrom(
  pages: readonly MessagePage[],
  appliedPageCount: number
): PharmaUIMessage[] {
  return pages
    .slice(appliedPageCount)
    .toReversed()
    .flatMap((page) => page.items.map(toPharmaMessage))
}

/** The concatenated text parts of a message, without sources or data parts. */
export function textOf(message: PharmaUIMessage): string {
  return message.parts
    .flatMap((part) => (part.type === "text" ? [part.text] : []))
    .join("")
}

/** The text of the last user message before the given answer, or undefined if there is none. */
export function questionBefore(
  messages: readonly PharmaUIMessage[],
  assistantMessageId: string
): string | undefined {
  const position = messages.findIndex(
    (message) => message.id === assistantMessageId
  )
  for (let index = position - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message?.role === "user") {
      return textOf(message)
    }
  }
  return undefined
}

/** Returns the messages with the given message's feedback replaced; messages without metadata are left as they are. */
export function withFeedback(
  messages: readonly PharmaUIMessage[],
  messageId: string,
  feedback: MessageFeedback | null
): PharmaUIMessage[] {
  return messages.map((message) =>
    message.id === messageId && message.metadata !== undefined
      ? { ...message, metadata: { ...message.metadata, feedback } }
      : message
  )
}

/** Removes the last turn: a trailing assistant message, then the user message before it. */
export function dropTrailingTurn(
  messages: readonly PharmaUIMessage[]
): PharmaUIMessage[] {
  const withoutAssistant =
    messages.at(-1)?.role === "assistant"
      ? messages.length - 1
      : messages.length
  const end =
    messages[withoutAssistant - 1]?.role === "user"
      ? withoutAssistant - 1
      : withoutAssistant
  return messages.slice(0, end)
}
