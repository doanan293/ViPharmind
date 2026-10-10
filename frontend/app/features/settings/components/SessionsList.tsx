import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"

import {
  getAccountSessionsListQueryKey,
  useAccountSessionsList,
  useAccountSessionsRevoke,
  useAccountSessionsRevokeOthers,
} from "~/api/gen/endpoints"
import type { SessionView } from "~/api/gen/schemas"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Spinner } from "~/components/ui/spinner"
import { Alert, AlertDescription } from "~/components/ui/alert"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "~/components/ui/item"

const BROWSERS = ["Edg", "Chrome", "Firefox", "Safari"] as const

/** A short device name from the user agent, enough to tell sessions apart. */
function browserOf(session: SessionView): string {
  const name = BROWSERS.find((browser) =>
    session.user_agent.includes(`${browser}/`)
  )
  return name === "Edg" ? "Edge" : (name ?? session.user_agent.slice(0, 40))
}

export function SessionsList() {
  const { t, i18n } = useTranslation("settings")
  const queryClient = useQueryClient()
  const sessions = useAccountSessionsList()
  const revoke = useAccountSessionsRevoke()
  const revokeOthers = useAccountSessionsRevokeOthers()
  const refresh = () =>
    queryClient.invalidateQueries({
      queryKey: getAccountSessionsListQueryKey(),
    })
  const format = new Intl.DateTimeFormat(i18n.language, {
    dateStyle: "medium",
    timeStyle: "short",
  })

  if (sessions.isError) {
    return (
      <div className="flex flex-col items-start gap-2 text-sm">
        <Alert variant="destructive">
          <AlertDescription>{t("sessions.loadFailed")}</AlertDescription>
        </Alert>
        <Button
          type="button"
          variant="outline"
          disabled={sessions.isFetching}
          onClick={() => void sessions.refetch()}
        >
          {t("sessions.retry")}
        </Button>
      </div>
    )
  }
  if (sessions.data === undefined) {
    return <Spinner />
  }
  return (
    <div className="flex flex-col gap-3">
      <ItemGroup className="gap-2">
        {sessions.data.map((session) => (
          <Item key={session.id} variant="outline" size="sm">
            <ItemContent>
              <ItemTitle>
                {browserOf(session)}
                {session.current ? (
                  <Badge variant="secondary">{t("sessions.current")}</Badge>
                ) : null}
              </ItemTitle>
              <ItemDescription>
                {session.ip_address} ·{" "}
                {format.format(
                  new Date(session.last_used_at ?? session.created_at)
                )}
              </ItemDescription>
            </ItemContent>
            {session.current ? null : (
              <ItemActions>
                <Button
                  type="button"
                  variant="outline"
                  aria-label={t("sessions.revokeOne", {
                    device: browserOf(session),
                  })}
                  onClick={() =>
                    void revoke
                      .mutateAsync({ sessionId: session.id })
                      .then(refresh)
                  }
                >
                  {t("sessions.revoke")}
                </Button>
              </ItemActions>
            )}
          </Item>
        ))}
      </ItemGroup>
      {sessions.data.some((session) => !session.current) ? (
        <Button
          type="button"
          variant="outline"
          className="self-start"
          onClick={() => void revokeOthers.mutateAsync().then(refresh)}
        >
          {t("sessions.revokeOthers")}
        </Button>
      ) : null}
    </div>
  )
}
