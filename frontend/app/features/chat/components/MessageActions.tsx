import { useQueryClient } from "@tanstack/react-query"
import { CheckIcon, CopyIcon, ThumbsDownIcon, ThumbsUpIcon } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import { useSubmitFeedback } from "~/api/gen/endpoints"
import type { MessageFeedback } from "~/api/gen/schemas"
import { Button } from "~/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog"
import { toast } from "~/components/ui/toast"
import { setMessageFeedbackInCache } from "~/features/conversations/lib/conversation-cache"
import { cn } from "~/lib/utils"

import { composeFeedbackNote } from "../lib/feedback-note"

import { FeedbackDialog, type FeedbackReason } from "./elements/feedback-dialog"
/** Props of `MessageActions`: the answer they act on and its current feedback. */
export type MessageActionsProps = {
  conversationId: string
  messageId: string
  /** The answer text that the copy button puts on the clipboard. */
  text: string
  feedback: MessageFeedback | null
  /** Called optimistically with the new feedback, and with the old one if saving fails. */
  onFeedbackChange: (
    messageId: string,
    feedback: MessageFeedback | null
  ) => void
}

const COPIED_RESET_MS = 2000

function CopyButton({ text }: { text: string }) {
  const { t } = useTranslation("chat")
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) {
      return undefined
    }
    const timer = window.setTimeout(() => setCopied(false), COPIED_RESET_MS)
    return () => window.clearTimeout(timer)
  }, [copied])

  async function copy() {
    await navigator.clipboard.writeText(text)
    setCopied(true)
  }

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label={copied ? t("actions.copied") : t("actions.copy")}
      onClick={() => void copy()}
    >
      {copied ? <CheckIcon aria-hidden /> : <CopyIcon aria-hidden />}
    </Button>
  )
}

type FeedbackTarget = Omit<MessageActionsProps, "text">

function useApplyFeedback({
  conversationId,
  messageId,
  feedback,
  onFeedbackChange,
}: FeedbackTarget): (next: MessageFeedback) => void {
  const { t } = useTranslation("chat")
  const queryClient = useQueryClient()
  const submitFeedback = useSubmitFeedback()

  return (next: MessageFeedback) => {
    const previous = feedback
    onFeedbackChange(messageId, next)
    setMessageFeedbackInCache(queryClient, conversationId, messageId, next)
    submitFeedback.mutate(
      { messageId, data: next },
      {
        onError: () => {
          onFeedbackChange(messageId, previous)
          setMessageFeedbackInCache(
            queryClient,
            conversationId,
            messageId,
            previous
          )
          toast.add({ title: t("actions.feedbackFailed"), type: "error" })
        },
      }
    )
  }
}

function useFeedbackReasons(): FeedbackReason[] {
  const { t } = useTranslation("chat")
  return useMemo<FeedbackReason[]>(
    () => [
      { id: "incorrect", label: t("feedback.reasons.incorrect") },
      { id: "incomplete", label: t("feedback.reasons.incomplete") },
      { id: "wrongSource", label: t("feedback.reasons.wrongSource") },
      { id: "unclear", label: t("feedback.reasons.unclear") },
    ],
    [t]
  )
}

function NotHelpfulDialog({
  apply,
  open,
  onOpenChange,
  draft,
}: {
  apply: (next: MessageFeedback) => void
  open: boolean
  onOpenChange: (open: boolean) => void
  draft: ReturnType<typeof useFeedbackDraft>
}) {
  const { t } = useTranslation("chat")
  const reasons = useFeedbackReasons()

  function sendDetails() {
    const labels = reasons
      .filter((reason) => draft.selected.includes(reason.id))
      .map((reason) => reason.label)
    apply({ rating: "down", note: composeFeedbackNote(labels, draft.note) })
    draft.setSent(true)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader className="sr-only">
          <DialogTitle>{t("feedback.title")}</DialogTitle>
        </DialogHeader>
        <FeedbackDialog
          reasons={reasons}
          selected={draft.selected}
          note={draft.note}
          sent={draft.sent}
          onToggleReason={draft.toggleReason}
          onNoteChange={draft.setNote}
          onSubmit={sendDetails}
        />
      </DialogContent>
    </Dialog>
  )
}

function useFeedbackDraft() {
  const [selected, setSelected] = useState<string[]>([])
  const [note, setNote] = useState("")
  const [sent, setSent] = useState(false)
  return {
    selected,
    note,
    sent,
    setNote,
    setSent,
    reset: () => {
      setSelected([])
      setNote("")
      setSent(false)
    },
    toggleReason: (id: string) => {
      setSelected((current) =>
        current.includes(id)
          ? current.filter((value) => value !== id)
          : [...current, id]
      )
    },
  }
}

/**
 * The footer actions of a finished answer: copy, thumbs up and thumbs down. Thumbs down
 * saves the rating at once and opens a dialog that can add reasons and a note.
 */
export function MessageActions({ text, ...target }: MessageActionsProps) {
  const { t } = useTranslation("chat")
  const apply = useApplyFeedback(target)
  const draft = useFeedbackDraft()
  const [dialogOpen, setDialogOpen] = useState(false)
  const rating = target.feedback?.rating

  function openNotHelpful() {
    draft.reset()
    setDialogOpen(true)
    apply({ rating: "down", note: "" })
  }

  return (
    <div className="flex items-center gap-0.5">
      <CopyButton text={text} />
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={t("actions.up")}
        aria-pressed={rating === "up"}
        onClick={() => apply({ rating: "up", note: "" })}
      >
        <ThumbsUpIcon
          aria-hidden
          className={cn(rating === "up" && "fill-current")}
        />
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={t("actions.down")}
        aria-pressed={rating === "down"}
        onClick={openNotHelpful}
      >
        <ThumbsDownIcon
          aria-hidden
          className={cn(rating === "down" && "fill-current")}
        />
      </Button>
      <NotHelpfulDialog
        apply={apply}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        draft={draft}
      />
    </div>
  )
}
