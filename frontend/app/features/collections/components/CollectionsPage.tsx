import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link, useNavigate } from "react-router"

import {
  useCollectionsCreate,
  useCollectionsList,
  useCollectionsQuota,
} from "~/api/gen/endpoints"
import type { CollectionView } from "~/api/gen/schemas"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { Progress } from "~/components/ui/progress"
import { Spinner } from "~/components/ui/spinner"
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

function CollectionList({
  title,
  items,
}: {
  title: string
  items: CollectionView[]
}) {
  const { t } = useTranslation("collections")
  if (items.length === 0) return null
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-lg font-medium">{title}</h2>
      <ItemGroup className="gap-2">
        {items.map((collection) => (
          <Item
            key={collection.id}
            variant="outline"
            render={<Link to={`/collections/${collection.id}`} />}
          >
            <ItemContent>
              <ItemTitle>{collection.title}</ItemTitle>
              <ItemDescription>{collection.owner_name}</ItemDescription>
            </ItemContent>
            <ItemActions>
              {collection.is_system ? (
                <Badge variant="secondary">{t("list.system")}</Badge>
              ) : null}
              <Badge variant="outline">
                {t(`visibility.${collection.visibility}`)}
              </Badge>
            </ItemActions>
          </Item>
        ))}
      </ItemGroup>
    </section>
  )
}

function QuotaBar() {
  const { t, i18n } = useTranslation("collections")
  const quota = useCollectionsQuota()
  if (quota.data === undefined) return null
  const numbers = new Intl.NumberFormat(i18n.language)
  const { text_used, text_limit, collections_used, collections_limit } =
    quota.data
  return (
    <div className="flex flex-col gap-1 text-sm text-muted-foreground">
      <span>
        {t("list.quota", {
          used: numbers.format(text_used),
          limit: numbers.format(text_limit),
          count: collections_used,
          max: collections_limit,
        })}
      </span>
      <Progress
        aria-label={t("list.quota", {
          used: numbers.format(text_used),
          limit: numbers.format(text_limit),
          count: collections_used,
          max: collections_limit,
        })}
        value={text_limit === 0 ? 100 : (100 * text_used) / text_limit}
      />
    </div>
  )
}

export function CollectionsPage() {
  const { t } = useTranslation("collections")
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const groups = useCollectionsList()
  const create = useCollectionsCreate()
  const [title, setTitle] = useState("")
  const [error, setError] = useState<string | null>(null)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    create.mutate(
      { data: { title: title.trim() } },
      {
        onSuccess: (created) => void navigate(`/collections/${created.id}`),
        onError: (failure) => setError(apiErrorMessage(failure, tErrors)),
      }
    )
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-4 md:p-8">
      <title>{t("list.title")}</title>
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">{t("list.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("list.description")}</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{t("list.create")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <form
            noValidate
            onSubmit={submit}
            className="flex flex-col gap-3 sm:flex-row sm:items-end"
          >
            <Field className="flex-1" data-invalid={error !== null}>
              <FieldLabel htmlFor="collection-title">
                {t("list.titleLabel")}
              </FieldLabel>
              <Input
                id="collection-title"
                value={title}
                maxLength={200}
                aria-invalid={error !== null}
                onChange={(event) => {
                  setTitle(event.target.value)
                  setError(null)
                }}
              />
              {error === null ? null : <FieldError>{error}</FieldError>}
            </Field>
            <Button
              type="submit"
              disabled={create.isPending || title.trim() === ""}
            >
              {t("list.create")}
            </Button>
          </form>
          <QuotaBar />
        </CardContent>
      </Card>
      {groups.data === undefined ? (
        <Spinner />
      ) : (
        <div className="flex flex-col gap-6">
          <CollectionList title={t("list.mine")} items={groups.data.mine} />
          {groups.data.organizations.map((group) => (
            <CollectionList
              key={group.organization_id}
              title={group.name}
              items={group.items}
            />
          ))}
          <CollectionList title={t("list.public")} items={groups.data.public} />
          <CollectionList title={t("list.others")} items={groups.data.others} />
          {groups.data.mine.length +
            groups.data.public.length +
            groups.data.others.length +
            groups.data.organizations.reduce(
              (total, group) => total + group.items.length,
              0
            ) ===
          0 ? (
            <Empty className="border">
              <EmptyHeader>
                <EmptyDescription>{t("list.empty")}</EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : null}
        </div>
      )}
    </div>
  )
}
