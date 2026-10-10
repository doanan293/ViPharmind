import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link, useNavigate } from "react-router"

import {
  useOrganizationsCreate,
  useOrganizationsList,
} from "~/api/gen/endpoints"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
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

export function OrganizationsPage() {
  const { t } = useTranslation("organizations")
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const organizations = useOrganizationsList()
  const create = useOrganizationsCreate()
  const [name, setName] = useState("")
  const [error, setError] = useState<string | null>(null)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = name.trim()
    if (trimmed === "") {
      setError(t("create.nameRequired"))
      return
    }
    create.mutate(
      { data: { name: trimmed } },
      {
        onSuccess: (created) => void navigate(`/organizations/${created.id}`),
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
          <CardTitle>{t("create.title")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            noValidate
            onSubmit={submit}
            className="flex flex-col gap-3 sm:flex-row sm:items-end"
          >
            <Field className="flex-1" data-invalid={error !== null}>
              <FieldLabel htmlFor="organization-name">
                {t("create.name")}
              </FieldLabel>
              <Input
                id="organization-name"
                value={name}
                maxLength={100}
                aria-invalid={error !== null}
                onChange={(event) => {
                  setName(event.target.value)
                  setError(null)
                }}
              />
              {error === null ? null : <FieldError>{error}</FieldError>}
            </Field>
            <Button type="submit" disabled={create.isPending}>
              {t("create.submit")}
            </Button>
          </form>
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
