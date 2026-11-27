import { type RefObject, useEffect, useRef, useState } from "react"

import type { MessagePage } from "~/api/gen/schemas"

import { olderMessagesFrom, prependOlder } from "../lib/chat-messages"
import type { PharmaUIMessage } from "../lib/message-schema"

type SetMessages = (
  update: (current: PharmaUIMessage[]) => PharmaUIMessage[]
) => void

/**
 * Prepends the messages of each newly fetched older history page to the thread. The first
 * page is the thread's initial messages, so only pages after it are applied, each once.
 */
export function usePrependOlderPages(
  pages: readonly MessagePage[],
  setMessages: SetMessages
): void {
  const appliedPagesRef = useRef(1)
  useEffect(() => {
    if (pages.length <= appliedPagesRef.current) {
      return
    }
    const older = olderMessagesFrom(pages, appliedPagesRef.current)
    appliedPagesRef.current = pages.length
    setMessages((current) => prependOlder(current, older))
  }, [pages, setMessages])
}

/** Inputs of `useSendInitialQuestion`. */
export type InitialQuestionOptions = {
  initialQuestion: string | undefined
  sendMessage: (message: { text: string }) => Promise<void>
  /** Receives the question, so a failed first stream can put it back into the composer. */
  lastQuestionRef: RefObject<string>
  onSent: () => void
}

/**
 * Sends the question a new chat was started with, once per mount, then calls `onSent` so the
 * caller can clear it from the location state.
 */
export function useSendInitialQuestion({
  initialQuestion,
  sendMessage,
  lastQuestionRef,
  onSent,
}: InitialQuestionOptions): void {
  const initialSentRef = useRef(false)
  useEffect(() => {
    if (initialQuestion === undefined || initialSentRef.current) {
      return
    }
    initialSentRef.current = true
    lastQuestionRef.current = initialQuestion
    void sendMessage({ text: initialQuestion })
    onSent()
  }, [initialQuestion, sendMessage, lastQuestionRef, onSent])
}

/**
 * Whether the thread content fits in the viewport without scrolling, kept current with a
 * ResizeObserver. Both refs must be attached on mount.
 */
export function useContentFits(
  viewportRef: RefObject<HTMLDivElement | null>,
  contentRef: RefObject<HTMLDivElement | null>
): boolean {
  const [contentFits, setContentFits] = useState(false)
  useEffect(() => {
    const viewport = viewportRef.current
    const content = contentRef.current
    if (viewport === null || content === null) {
      return undefined
    }
    const observer = new ResizeObserver(() => {
      setContentFits(viewport.scrollHeight <= viewport.clientHeight + 1)
    })
    observer.observe(viewport)
    observer.observe(content)
    return () => observer.disconnect()
  }, [viewportRef, contentRef])
  return contentFits
}
