import { MessageSquareTextIcon } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

import { updateConversation, useCreateConversation } from "~/api/gen/endpoints"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "~/components/ui/empty"
import { toast } from "~/components/ui/toast"

import type { ChatLocationState } from "../lib/location-state"

import { Composer } from "./Composer"
import { type SourceScope, SourcesPopover } from "./SourcesPopover"

export function NewChat() {
  const { t } = useTranslation("chat")
  const navigate = useNavigate()
  const [draft, setDraft] = useState("")
  const [sources, setSources] = useState<SourceScope>(null)
  const createConversation = useCreateConversation()

  function start(question: string) {
    createConversation.mutate(undefined, {
      onSuccess: async (conversation) => {
        // The scope must be saved before the first question streams.
        if (sources !== null) {
          await updateConversation(conversation.id, {
            collection_ids: sources,
          })
        }
        const state: ChatLocationState = { initialQuestion: question }
        await navigate(`/chat/${conversation.id}`, { replace: true, state })
      },
      onError: () => {
        toast.add({ title: t("newChat.createFailed"), type: "error" })
      },
    })
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <Empty className="flex-1">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <MessageSquareTextIcon aria-hidden />
          </EmptyMedia>
          <EmptyTitle>{t("newChat.title")}</EmptyTitle>
          <EmptyDescription>{t("newChat.description")}</EmptyDescription>
        </EmptyHeader>
      </Empty>
      <Composer
        value={draft}
        onValueChange={setDraft}
        busy={false}
        disabled={createConversation.isPending}
        error={null}
        onSubmit={start}
        onStop={() => undefined}
        leading={<SourcesPopover value={sources} onChange={setSources} />}
      />
    </div>
  )
}
