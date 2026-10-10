import { useTranslation } from "react-i18next"

import { useAdminConversationsMessagesInfinite } from "~/api/gen/endpoints"
import { Alert, AlertDescription } from "~/components/ui/alert"
import { Button } from "~/components/ui/button"
import { Spinner } from "~/components/ui/spinner"
import { MessageParts } from "~/features/chat/components/MessageParts"
import { olderMessagesFrom } from "~/features/chat/lib/chat-messages"
import { apiErrorMessage } from "~/i18n/error-message"

const noop = () => undefined

/** A user's conversation as they saw it, without retry, feedback or citation actions. */
export function ReadOnlyThread({
  userId,
  conversationId,
}: {
  userId: string
  conversationId: string
}) {
  const { t } = useTranslation("admin")
  const { t: tErrors } = useTranslation("errors")
  const query = useAdminConversationsMessagesInfinite(
    userId,
    conversationId,
    { limit: 50 },
    {
      query: {
        initialPageParam: undefined,
        getNextPageParam: (page) => page.next_cursor ?? undefined,
      },
    }
  )

  if (query.isError && query.data === undefined) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          {apiErrorMessage(query.error, tErrors)}
        </AlertDescription>
      </Alert>
    )
  }
  if (query.data === undefined) return <Spinner />
  // Pages run newest first; each page is in reading order.
  const messages = olderMessagesFrom(query.data.pages, 0)
  return (
    <div className="flex flex-col gap-4">
      {query.hasNextPage ? (
        <Button
          variant="outline"
          size="sm"
          className="self-center"
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
        >
          {t("users.more")}
        </Button>
      ) : null}
      {messages.map((message) => (
        <MessageParts
          key={message.id}
          message={message}
          streaming={false}
          stopped={false}
          failed={false}
          retrying={false}
          onRetry={noop}
          onOpenCitation={noop}
        />
      ))}
    </div>
  )
}
