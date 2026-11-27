import { createContext, type ReactNode, useContext } from "react"

import type { PharmaSourceMetadata } from "~/api/gen/schemas"

/** The cited sources of one answer, by citation number, and how to open one in the citation sheet. */
export type MessageCitations = {
  messageId: string
  sources: ReadonlyMap<number, PharmaSourceMetadata>
  openCitation: (index: number) => void
}

const MessageCitationsContext = createContext<MessageCitations | null>(null)

/** Gives the citation markers rendered inside an answer access to that answer's sources. */
export function MessageCitationsProvider({
  value,
  children,
}: {
  value: MessageCitations
  children: ReactNode
}) {
  return (
    <MessageCitationsContext value={value}>{children}</MessageCitationsContext>
  )
}

/** The citations of the surrounding answer, or null outside a `MessageCitationsProvider`. */
export function useMessageCitations(): MessageCitations | null {
  return useContext(MessageCitationsContext)
}
