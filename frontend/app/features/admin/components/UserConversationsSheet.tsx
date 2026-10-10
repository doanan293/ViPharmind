import { ArrowLeftIcon } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { useAdminUsersConversationsInfinite } from "~/api/gen/endpoints"
import type { AdminUserView } from "~/api/gen/schemas"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Empty, EmptyDescription, EmptyHeader } from "~/components/ui/empty"
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "~/components/ui/item"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "~/components/ui/sheet"
import { Spinner } from "~/components/ui/spinner"

import { ReadOnlyThread } from "./ReadOnlyThread"

function ConversationList({
  userId,
  onOpen,
}: {
  userId: string
  onOpen: (conversationId: string) => void
}) {
  const { t, i18n } = useTranslation("admin")
  const format = new Intl.DateTimeFormat(i18n.language, {
    dateStyle: "medium",
    timeStyle: "short",
  })
  const query = useAdminUsersConversationsInfinite(
    userId,
    { limit: 30 },
    {
      query: {
        initialPageParam: undefined,
        getNextPageParam: (page) => page.next_cursor ?? undefined,
      },
    }
  )
  if (query.data === undefined) return <Spinner />
  const items = query.data.pages.flatMap((page) => page.items)
  if (items.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyDescription>{t("conversations.empty")}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }
  return (
    <ItemGroup className="gap-2">
      {items.map((conversation) => (
        <Item
          key={conversation.id}
          variant="outline"
          size="sm"
          render={(props) => <button type="button" {...props} />}
          onClick={() => onOpen(conversation.id)}
          className="text-start"
        >
          <ItemContent>
            <ItemTitle>{conversation.title}</ItemTitle>
            <ItemDescription>
              {t("conversations.turns", { count: conversation.turn_count })} ·{" "}
              {format.format(new Date(conversation.updated_at))}
            </ItemDescription>
          </ItemContent>
        </Item>
      ))}
      {query.hasNextPage ? (
        <Button
          variant="outline"
          size="sm"
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
        >
          {t("users.more")}
        </Button>
      ) : null}
    </ItemGroup>
  )
}

/** A user's conversations, opened one at a time in read-only form. */
export function UserConversationsSheet({
  user,
  onClose,
}: {
  user: AdminUserView | null
  onClose: () => void
}) {
  const { t } = useTranslation("admin")
  const [conversationId, setConversationId] = useState<string | null>(null)
  return (
    <Sheet
      open={user !== null}
      onOpenChange={(open) => {
        if (!open) {
          setConversationId(null)
          onClose()
        }
      }}
    >
      <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>
            {t("conversations.title", { name: user?.display_name ?? "" })}
          </SheetTitle>
          <SheetDescription>
            <Badge variant="secondary">{t("conversations.readOnly")}</Badge>
          </SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-4 px-4 pb-4">
          {user === null ? null : conversationId === null ? (
            <ConversationList userId={user.id} onOpen={setConversationId} />
          ) : (
            <>
              <Button
                variant="ghost"
                size="sm"
                className="self-start"
                onClick={() => setConversationId(null)}
              >
                <ArrowLeftIcon data-icon="inline-start" />
                {t("conversations.back")}
              </Button>
              <ReadOnlyThread
                userId={user.id}
                conversationId={conversationId}
              />
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
