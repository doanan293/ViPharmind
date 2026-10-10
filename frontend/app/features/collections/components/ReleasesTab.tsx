import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"

import {
  getCollectionsGetQueryKey,
  getCollectionsReleasesQueryKey,
  useCollectionsReleases,
  useCollectionsRollback,
} from "~/api/gen/endpoints"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Spinner } from "~/components/ui/spinner"
import { toast } from "~/components/ui/toast"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "~/components/ui/item"
import { Empty, EmptyDescription, EmptyHeader } from "~/components/ui/empty"
import { apiErrorMessage } from "~/i18n/error-message"

export function ReleasesTab({
  collectionId,
  editable,
}: {
  collectionId: string
  editable: boolean
}) {
  const { t, i18n } = useTranslation("collections")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const releases = useCollectionsReleases(collectionId)
  const rollback = useCollectionsRollback()
  const format = new Intl.DateTimeFormat(i18n.language, {
    dateStyle: "medium",
    timeStyle: "short",
  })

  if (releases.data === undefined) {
    return <Spinner />
  }
  if (releases.data.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyDescription>{t("releases.empty")}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }
  const current = releases.data.find((release) => release.current)
  const canRollBack =
    editable &&
    current !== undefined &&
    releases.data.some(
      (release) =>
        release.status === "retired" && release.number < current.number
    )

  return (
    <div className="flex flex-col gap-4">
      <ItemGroup className="gap-2">
        {releases.data.map((release) => (
          <Item key={release.id} variant="outline" size="sm">
            <ItemContent>
              <ItemTitle>
                {t("releases.number", { number: release.number })}
                {release.current ? (
                  <Badge>{t("releases.current")}</Badge>
                ) : null}
              </ItemTitle>
            </ItemContent>
            <ItemActions>
              <ItemDescription>
                {format.format(
                  new Date(release.published_at ?? release.created_at)
                )}
              </ItemDescription>
            </ItemActions>
          </Item>
        ))}
      </ItemGroup>
      {canRollBack ? (
        <Button
          variant="outline"
          className="self-start"
          disabled={rollback.isPending}
          onClick={() =>
            rollback.mutate(
              { collectionId },
              {
                onSuccess: (release) => {
                  toast.add({
                    type: "success",
                    title: t("releases.rolledBack", { number: release.number }),
                  })
                  void queryClient.invalidateQueries({
                    queryKey: getCollectionsReleasesQueryKey(collectionId),
                  })
                  void queryClient.invalidateQueries({
                    queryKey: getCollectionsGetQueryKey(collectionId),
                  })
                },
                onError: (error) =>
                  toast.add({
                    type: "error",
                    title: apiErrorMessage(error, tErrors),
                  }),
              }
            )
          }
        >
          {t("releases.rollback")}
        </Button>
      ) : null}
    </div>
  )
}
