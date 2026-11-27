import type {
  InfiniteData,
  UseInfiniteQueryResult,
} from "@tanstack/react-query"
import {
  MoreHorizontalIcon,
  PencilIcon,
  PlusIcon,
  Trash2Icon,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useInView } from "react-intersection-observer"
import { Link, NavLink, useParams } from "react-router"

import { useListConversationsInfinite } from "~/api/gen/endpoints"
import type {
  ConversationPage,
  ConversationView,
  ListConversationsParams,
  Problem,
} from "~/api/gen/schemas"
import { Alert, AlertDescription } from "~/components/ui/alert"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "~/components/ui/dropdown-menu"
import {
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
} from "~/components/ui/sidebar"

import { DeleteConversationDialog } from "./DeleteConversationDialog"
import { RenameConversationDialog } from "./RenameConversationDialog"

const CONVERSATION_PAGE_SIZE = 20

type PendingAction = {
  kind: "rename" | "delete"
  conversation: ConversationView
} | null

type ConversationPages = InfiniteData<
  ConversationPage,
  ListConversationsParams["cursor"]
>

const SKELETON_KEYS = ["first", "second", "third"] as const

function ConversationItem({
  conversation,
  active,
  onAction,
}: {
  conversation: ConversationView
  active: boolean
  onAction: (kind: "rename" | "delete") => void
}) {
  const { t } = useTranslation("chat")
  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        render={<NavLink to={`/chat/${conversation.id}`} />}
        isActive={active}
      >
        <span className="truncate">{conversation.title}</span>
      </SidebarMenuButton>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <SidebarMenuAction
              showOnHover
              aria-label={t("conversations.more", {
                title: conversation.title,
              })}
            />
          }
        >
          <MoreHorizontalIcon aria-hidden />
        </DropdownMenuTrigger>
        <DropdownMenuContent side="right" align="start">
          <DropdownMenuItem onClick={() => onAction("rename")}>
            <PencilIcon aria-hidden />
            {t("conversations.rename")}
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            onClick={() => onAction("delete")}
          >
            <Trash2Icon aria-hidden />
            {t("conversations.delete")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuItem>
  )
}

/**
 * The sidebar's list of the user's conversations, loading further pages as
 * the list scrolls, with rename and delete actions. Reads the open conversation
 * from the route's `conversationId` param to mark it active.
 */
export function ConversationSidebar() {
  const { t } = useTranslation("chat")
  const { conversationId } = useParams()
  const [pending, setPending] = useState<PendingAction>(null)
  // Typed explicitly: without `initialData` the pages are undefined until the
  // first one loads, which the generated hook's first overload hides.
  const query: UseInfiniteQueryResult<ConversationPages, Problem> =
    useListConversationsInfinite<ConversationPages, Problem>(
      { limit: CONVERSATION_PAGE_SIZE },
      {
        query: {
          initialPageParam: undefined,
          getNextPageParam: (page) => page.next_cursor ?? undefined,
        },
      }
    )
  const {
    data,
    isPending,
    isError,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  } = query
  const { ref: sentinelRef, inView } = useInView({ rootMargin: "120px" })

  useEffect(() => {
    if (inView && hasNextPage && !isFetchingNextPage) {
      void fetchNextPage()
    }
  }, [inView, hasNextPage, isFetchingNextPage, fetchNextPage])

  const conversations = data?.pages.flatMap((page) => page.items) ?? []

  return (
    <SidebarGroup className="group-data-[collapsible=icon]:hidden">
      <SidebarGroupLabel>{t("conversations.title")}</SidebarGroupLabel>
      <SidebarGroupAction
        render={<Link to="/chat" />}
        aria-label={t("conversations.new")}
      >
        <PlusIcon aria-hidden />
      </SidebarGroupAction>
      <SidebarGroupContent>
        <SidebarMenu>
          {isPending
            ? SKELETON_KEYS.map((key) => (
                <SidebarMenuItem key={key}>
                  <SidebarMenuSkeleton />
                </SidebarMenuItem>
              ))
            : null}
          {isError && data === undefined ? (
            <SidebarMenuItem>
              <Alert variant="destructive" className="mx-2 w-auto text-xs">
                <AlertDescription>
                  {t("conversations.loadFailed")}
                </AlertDescription>
              </Alert>
            </SidebarMenuItem>
          ) : null}
          {data !== undefined && conversations.length === 0 ? (
            <SidebarMenuItem>
              <p className="px-2 text-xs text-muted-foreground">
                {t("conversations.empty")}
              </p>
            </SidebarMenuItem>
          ) : null}
          {conversations.map((conversation) => (
            <ConversationItem
              key={conversation.id}
              conversation={conversation}
              active={conversation.id === conversationId}
              onAction={(kind) => setPending({ kind, conversation })}
            />
          ))}
          {hasNextPage ? (
            <SidebarMenuItem ref={sentinelRef}>
              <SidebarMenuSkeleton />
            </SidebarMenuItem>
          ) : null}
        </SidebarMenu>
      </SidebarGroupContent>
      <RenameConversationDialog
        conversation={pending?.kind === "rename" ? pending.conversation : null}
        onClose={() => setPending(null)}
      />
      <DeleteConversationDialog
        conversation={pending?.kind === "delete" ? pending.conversation : null}
        activeConversationId={conversationId}
        onClose={() => setPending(null)}
      />
    </SidebarGroup>
  )
}
