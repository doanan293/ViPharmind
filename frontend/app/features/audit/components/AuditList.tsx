import type {
  InfiniteData,
  UseInfiniteQueryResult,
} from "@tanstack/react-query"
import { useTranslation } from "react-i18next"

import type { AuditPage, Problem } from "~/api/gen/schemas"
import { Button } from "~/components/ui/button"
import { Spinner } from "~/components/ui/spinner"

import { describeEvent } from "../lib/describe-event"

export type AuditQuery = UseInfiniteQueryResult<
  InfiniteData<AuditPage, string | null | undefined>,
  Problem
>

/** Any audit log: an organization's, the user's own, or the whole system's. */
export function AuditList({ query }: { query: AuditQuery }) {
  const { t, i18n } = useTranslation("audit")
  const format = new Intl.DateTimeFormat(i18n.language, {
    dateStyle: "medium",
    timeStyle: "short",
  })
  if (query.isPending) {
    return <Spinner />
  }
  if (query.isError && query.data === undefined) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t("page.failed")}
      </p>
    )
  }
  const events = query.data?.pages.flatMap((page) => page.items) ?? []
  if (events.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("page.empty")}</p>
  }
  return (
    <div className="flex flex-col gap-3">
      <ol className="flex flex-col gap-2">
        {events.map((event) => (
          <li key={event.id} className="flex flex-col text-sm">
            <span>{describeEvent(event, t)}</span>
            <time
              dateTime={event.occurred_at}
              className="text-xs text-muted-foreground"
            >
              {format.format(new Date(event.occurred_at))}
            </time>
          </li>
        ))}
      </ol>
      {query.hasNextPage ? (
        <Button
          type="button"
          variant="outline"
          className="self-start"
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
        >
          {t("page.loadMore")}
        </Button>
      ) : null}
    </div>
  )
}
