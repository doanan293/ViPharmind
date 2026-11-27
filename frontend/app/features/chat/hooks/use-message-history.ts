import type {
  InfiniteData,
  UseInfiniteQueryResult,
} from "@tanstack/react-query"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

import { useListMessagesInfinite } from "~/api/gen/endpoints"
import type { MessagePage, Problem } from "~/api/gen/schemas"
import { isApiError } from "~/api/problem"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"

const HISTORY_PAGE_SIZE = 30

/** The paged message history query of one conversation, newest page first. */
export type MessageHistory = UseInfiniteQueryResult<
  InfiniteData<MessagePage, string | null | undefined> | undefined,
  Problem | null
>

/**
 * Loads a conversation's messages page by page, newest first, once per mount (no refetch on
 * focus or reconnect). When the conversation does not exist it shows a toast and goes to
 * `/chat`; `notFound` tells the caller to render nothing meanwhile.
 */
export function useMessageHistory(conversationId: string): {
  history: MessageHistory
  notFound: boolean
} {
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  // The annotation picks the overload without initial data, where `data` can be missing.
  const history: MessageHistory = useListMessagesInfinite(
    conversationId,
    { limit: HISTORY_PAGE_SIZE },
    {
      query: {
        initialPageParam: undefined,
        getNextPageParam: (page) => page.next_cursor ?? undefined,
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: 0,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
      },
    }
  )
  const { error } = history
  const notFound = isApiError(error) && error.code === "CONVERSATION_NOT_FOUND"

  useEffect(() => {
    if (!notFound) {
      return
    }
    toast.add({ title: apiErrorMessage(error, tErrors), type: "error" })
    void navigate("/chat", { replace: true })
  }, [notFound, error, navigate, tErrors])

  return { history, notFound }
}
