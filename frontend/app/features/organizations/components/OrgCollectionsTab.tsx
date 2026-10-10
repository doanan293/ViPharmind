import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { Link } from "react-router"

import {
  getCollectionsListQueryKey,
  useCollectionsCreate,
  useCollectionsList,
} from "~/api/gen/endpoints"
import { NameForm } from "~/components/name-form"
import { Badge } from "~/components/ui/badge"
import { Spinner } from "~/components/ui/spinner"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemGroup,
  ItemTitle,
} from "~/components/ui/item"
import { Empty, EmptyDescription, EmptyHeader } from "~/components/ui/empty"

import { type Viewer, atLeast } from "../lib/roles"

export function OrgCollectionsTab({
  organizationId,
  viewer,
}: {
  organizationId: string
  viewer: Viewer
}) {
  const { t } = useTranslation("organizations")
  const queryClient = useQueryClient()
  const groups = useCollectionsList()
  const create = useCollectionsCreate()
  const canCreate = atLeast(viewer, "editor")

  if (groups.data === undefined) {
    return <Spinner />
  }
  const items =
    groups.data.organizations.find(
      (group) => group.organization_id === organizationId
    )?.items ?? []
  return (
    <div className="flex flex-col gap-6">
      {canCreate ? (
        <NameForm
          id="org-collection-title"
          field="title"
          label={t("collections.title")}
          submitLabel={t("collections.create")}
          requiredMessage={t("collections.titleRequired")}
          maxLength={200}
          onSubmit={async (title) => {
            await create.mutateAsync({
              data: { title, owner_organization_id: organizationId },
            })
            await queryClient.invalidateQueries({
              queryKey: getCollectionsListQueryKey(),
            })
          }}
        />
      ) : null}
      {items.length === 0 ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyDescription>{t("collections.empty")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <ItemGroup className="gap-2">
          {items.map((collection) => (
            <Item
              key={collection.id}
              variant="outline"
              size="sm"
              render={<Link to={`/collections/${collection.id}`} />}
            >
              <ItemContent>
                <ItemTitle>{collection.title}</ItemTitle>
              </ItemContent>
              <ItemActions>
                <Badge variant="secondary">
                  {collection.visibility === "organization"
                    ? t("collections.shared")
                    : t("collections.private")}
                </Badge>
              </ItemActions>
            </Item>
          ))}
        </ItemGroup>
      )}
    </div>
  )
}
