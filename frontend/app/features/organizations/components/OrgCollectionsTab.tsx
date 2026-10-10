import { useQueryClient } from "@tanstack/react-query"
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router"

import {
  getCollectionsListQueryKey,
  useCollectionsCreate,
  useCollectionsList,
} from "~/api/gen/endpoints"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Field, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { Spinner } from "~/components/ui/spinner"
import { toast } from "~/components/ui/toast"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemGroup,
  ItemTitle,
} from "~/components/ui/item"
import { Empty, EmptyDescription, EmptyHeader } from "~/components/ui/empty"
import { apiErrorMessage } from "~/i18n/error-message"

import { type Viewer, atLeast } from "../lib/roles"

export function OrgCollectionsTab({
  organizationId,
  viewer,
}: {
  organizationId: string
  viewer: Viewer
}) {
  const { t } = useTranslation("organizations")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const groups = useCollectionsList()
  const create = useCollectionsCreate()
  const [title, setTitle] = useState("")
  const canCreate = atLeast(viewer, "editor")

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    create.mutate(
      { data: { title: title.trim(), owner_organization_id: organizationId } },
      {
        onSuccess: () => {
          setTitle("")
          void queryClient.invalidateQueries({
            queryKey: getCollectionsListQueryKey(),
          })
        },
        onError: (error) =>
          toast.add({ type: "error", title: apiErrorMessage(error, tErrors) }),
      }
    )
  }

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
        <form
          onSubmit={submit}
          className="flex flex-col gap-3 sm:flex-row sm:items-end"
        >
          <Field className="flex-1">
            <FieldLabel htmlFor="org-collection-title">
              {t("collections.title")}
            </FieldLabel>
            <Input
              id="org-collection-title"
              value={title}
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
            />
          </Field>
          <Button
            type="submit"
            disabled={create.isPending || title.trim() === ""}
          >
            {t("collections.create")}
          </Button>
        </form>
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
