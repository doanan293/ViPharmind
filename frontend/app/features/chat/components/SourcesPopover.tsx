import { useQueryClient } from "@tanstack/react-query"
import { LibraryIcon } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import {
  getGetConversationQueryKey,
  useCollectionsList,
  useGetConversation,
  useUpdateConversation,
} from "~/api/gen/endpoints"
import type { CollectionGroups, CollectionView } from "~/api/gen/schemas"
import { Button } from "~/components/ui/button"
import {
  Combobox,
  ComboboxCollection,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxGroup,
  ComboboxInput,
  ComboboxItem,
  ComboboxLabel,
  ComboboxList,
  ComboboxTrigger,
} from "~/components/ui/combobox"
import { toast } from "~/components/ui/toast"
import { replaceConversationInCache } from "~/features/conversations/lib/conversation-cache"

/** `null` searches everything the user can see; a list narrows the search to it. */
export type SourceScope = string[] | null

interface Group {
  key: string
  title: string
  items: CollectionView[]
}

function groupsOf(
  groups: CollectionGroups,
  titles: { public: string; mine: string; others: string }
): Group[] {
  return [
    { key: "public", title: titles.public, items: groups.public },
    ...groups.organizations.map((group) => ({
      key: group.organization_id,
      title: group.name,
      items: group.items,
    })),
    { key: "mine", title: titles.mine, items: groups.mine },
    { key: "others", title: titles.others, items: groups.others },
  ].filter((group) => group.items.length > 0)
}

/**
 * Picks the collections a conversation searches, as a shadcn multi-select combobox. No pick
 * means everything the user can see; removing the last pick goes back to that.
 */
export function SourcesPopover({
  value,
  onChange,
}: {
  value: SourceScope
  onChange: (value: SourceScope) => void
}) {
  const { t } = useTranslation("chat")
  const [opened, setOpened] = useState(false)
  // Load the collections only once the picker is opened.
  const groups = useCollectionsList({ query: { enabled: opened } }).data
  const grouped =
    groups === undefined
      ? []
      : groupsOf(groups, {
          public: t("scope.public"),
          mine: t("scope.mine"),
          others: t("scope.others"),
        })
  const all = grouped.flatMap((group) => group.items)
  const selected = all.filter((item) => value?.includes(item.id) === true)
  // A combobox takes no name from its content, so the trigger repeats its text as the label.
  const label =
    value === null
      ? t("scope.button")
      : t("scope.buttonCount", { count: value.length })

  return (
    <Combobox
      multiple
      onOpenChange={(open) => {
        if (open) setOpened(true)
      }}
      items={grouped}
      value={selected}
      onValueChange={(next: CollectionView[]) =>
        onChange(next.length === 0 ? null : next.map((item) => item.id))
      }
      itemToStringLabel={(item: CollectionView) => item.title}
      isItemEqualToValue={(item: CollectionView, other: CollectionView) =>
        item.id === other.id
      }
    >
      <ComboboxTrigger
        aria-label={label}
        render={<Button variant="ghost" size="sm" />}
      >
        <LibraryIcon aria-hidden data-icon="inline-start" />
        {label}
      </ComboboxTrigger>
      <ComboboxContent className="w-80">
        <ComboboxInput showTrigger={false} placeholder={t("scope.search")} />
        <Button
          variant={value === null ? "secondary" : "ghost"}
          size="sm"
          className="mx-1 mt-1 justify-start"
          aria-pressed={value === null}
          onClick={() => {
            if (value !== null) onChange(null)
          }}
        >
          {t("scope.all")}
        </Button>
        <ComboboxEmpty>{t("scope.empty")}</ComboboxEmpty>
        <ComboboxList>
          {(group: Group) => (
            <ComboboxGroup key={group.key} items={group.items}>
              <ComboboxLabel>{group.title}</ComboboxLabel>
              <ComboboxCollection>
                {(item: CollectionView) => (
                  <ComboboxItem key={item.id} value={item}>
                    {item.title}
                  </ComboboxItem>
                )}
              </ComboboxCollection>
            </ComboboxGroup>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}

/** The sources of a saved conversation, saved on every change. */
export function ConversationSources({
  conversationId,
}: {
  conversationId: string
}) {
  const { t } = useTranslation("chat")
  const queryClient = useQueryClient()
  const conversation = useGetConversation(conversationId)
  const update = useUpdateConversation()

  return (
    <SourcesPopover
      value={conversation.data?.collection_ids ?? null}
      onChange={(collectionIds) =>
        update.mutate(
          { conversationId, data: { collection_ids: collectionIds } },
          {
            onSuccess: (updated) => {
              queryClient.setQueryData(
                getGetConversationQueryKey(conversationId),
                updated
              )
              replaceConversationInCache(queryClient, updated)
            },
            onError: () =>
              toast.add({ type: "error", title: t("scope.saveFailed") }),
          }
        )
      }
    />
  )
}
