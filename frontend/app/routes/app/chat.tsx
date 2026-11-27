import {
  ChatThread,
  ChatThreadFallback,
} from "~/features/chat/components/ChatThread"

import type { Route } from "./+types/chat"

/** Reads the conversation id from the URL; `null` starts a new conversation. */
export function clientLoader({ params }: Route.ClientLoaderArgs) {
  return { conversationId: params.conversationId ?? null }
}

/** The chat skeleton shown until the client loader has run. */
export function HydrateFallback() {
  return <ChatThreadFallback />
}

/**
 * The chat page at `/chat/:conversationId?`, sized to the viewport below the shell header.
 */
export default function ChatRoute({ loaderData }: Route.ComponentProps) {
  return (
    <div className="flex h-[calc(100svh-3rem)] min-h-0 flex-col">
      <ChatThread conversationId={loaderData.conversationId ?? undefined} />
    </div>
  )
}
