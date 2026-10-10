import { useTranslation } from "react-i18next"
import { Link, useNavigate } from "react-router"

import {
  useOrganizationsCreate,
  useOrganizationsList,
} from "~/api/gen/endpoints"
import { NameForm } from "~/components/name-form"
import { Badge } from "~/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
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

export function OrganizationsPage() {
  const { t } = useTranslation("organizations")
  const navigate = useNavigate()
  const organizations = useOrganizationsList()
  const create = useOrganizationsCreate()

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-4 md:p-8">
      <title>{t("list.title")}</title>
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">{t("list.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("list.description")}</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{t("create.title")}</CardTitle>
        </CardHeader>
        <CardContent>
          <NameForm
            id="organization-name"
            field="name"
            label={t("create.name")}
            submitLabel={t("create.submit")}
            requiredMessage={t("create.nameRequired")}
            maxLength={100}
            onSubmit={async (name) => {
              const created = await create.mutateAsync({ data: { name } })
              await navigate(`/organizations/${created.id}`)
            }}
          />
        </CardContent>
      </Card>
      {organizations.data === undefined ? (
        <Spinner />
      ) : organizations.data.length === 0 ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyDescription>{t("list.empty")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <ItemGroup className="gap-2">
          {organizations.data.map((organization) => (
            <Item
              key={organization.id}
              variant="outline"
              render={<Link to={`/organizations/${organization.id}`} />}
            >
              <ItemContent>
                <ItemTitle>{organization.name}</ItemTitle>
                <ItemDescription>
                  {t("list.members", { count: organization.member_count })}
                </ItemDescription>
              </ItemContent>
              <ItemActions>
                <Badge variant="secondary">
                  {t(`role.${organization.role ?? "admin"}`)}
                </Badge>
              </ItemActions>
            </Item>
          ))}
        </ItemGroup>
      )}
    </div>
  )
}
