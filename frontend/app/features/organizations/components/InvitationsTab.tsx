import { useQueryClient } from "@tanstack/react-query"
import { zodResolver } from "@hookform/resolvers/zod"
import { useState } from "react"
import { Controller, useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"

import {
  getInvitationsListQueryKey,
  useInvitationsApprove,
  useInvitationsCreate,
  useInvitationsList,
  useInvitationsReject,
  useInvitationsResend,
  useInvitationsRevoke,
} from "~/api/gen/endpoints"
import { InvitationsCreateBody } from "~/api/gen/zod"
import type { InvitationView } from "~/api/gen/schemas"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { NativeSelect, NativeSelectOption } from "~/components/ui/native-select"
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
import { applyApiError } from "~/lib/form-errors"

import { type Viewer, atLeast, invitableRoles } from "../lib/roles"

export function InvitationsTab({
  organizationId,
  viewer,
  currentUserId,
}: {
  organizationId: string
  viewer: Viewer
  currentUserId: string
}) {
  const { t, i18n } = useTranslation("organizations")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const invitations = useInvitationsList(organizationId)
  const create = useInvitationsCreate()
  const approve = useInvitationsApprove()
  const reject = useInvitationsReject()
  const revoke = useInvitationsRevoke()
  const resend = useInvitationsResend()
  const roles = invitableRoles(viewer)
  const form = useForm({
    resolver: zodResolver(InvitationsCreateBody),
    defaultValues: { email: "", role: "member" as const },
  })
  const serverError = form.formState.errors.root?.server?.message
  const [notice, setNotice] = useState<string | null>(null)
  const canDecide = atLeast(viewer, "editor")
  const format = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" })

  const refresh = () =>
    queryClient.invalidateQueries({
      queryKey: getInvitationsListQueryKey(organizationId),
    })
  const fail = (error: unknown) =>
    toast.add({ type: "error", title: apiErrorMessage(error, tErrors) })
  const act = {
    onSuccess: () => void refresh(),
    onError: fail,
  }

  async function onSubmit(data: {
    email: string
    role: InvitationView["role"]
  }) {
    try {
      const created = await create.mutateAsync({ organizationId, data })
      form.reset({ email: "", role: data.role })
      setNotice(
        created.status === "pending_approval"
          ? t("invitations.pending")
          : t("invitations.sent")
      )
      await refresh()
    } catch (error) {
      applyApiError(
        error,
        form.setError,
        ["email", "role"],
        apiErrorMessage(error, tErrors)
      )
    }
  }

  function actions(invitation: InvitationView) {
    const target = { organizationId, invitationId: invitation.id }
    const mine = invitation.invited_by === currentUserId
    if (invitation.status === "pending_approval") {
      return (
        <>
          {canDecide ? (
            <>
              <Button size="sm" onClick={() => approve.mutate(target, act)}>
                {t("invitations.approve")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => reject.mutate(target, act)}
              >
                {t("invitations.reject")}
              </Button>
            </>
          ) : null}
          {!canDecide && mine ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => revoke.mutate(target, act)}
            >
              {t("invitations.revoke")}
            </Button>
          ) : null}
        </>
      )
    }
    if (
      (invitation.status === "sent" || invitation.status === "expired") &&
      (canDecide || mine)
    ) {
      return (
        <>
          <Button
            size="sm"
            variant="outline"
            onClick={() => resend.mutate(target, act)}
          >
            {t("invitations.resend")}
          </Button>
          {invitation.status === "sent" ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => revoke.mutate(target, act)}
            >
              {t("invitations.revoke")}
            </Button>
          ) : null}
        </>
      )
    }
    return null
  }

  return (
    <div className="flex flex-col gap-6">
      {roles.length > 0 ? (
        <form
          noValidate
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-3 sm:flex-row sm:items-start"
        >
          <Controller
            name="email"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field className="flex-1" data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor="invite-email">
                  {t("invitations.email")}
                </FieldLabel>
                <Input
                  {...field}
                  id="invite-email"
                  type="email"
                  autoComplete="off"
                  aria-invalid={fieldState.invalid}
                />
                <FieldError errors={[fieldState.error]} />
                {serverError === undefined ? null : (
                  <FieldError>{serverError}</FieldError>
                )}
              </Field>
            )}
          />
          <Controller
            name="role"
            control={form.control}
            render={({ field }) => (
              <Field className="sm:w-48">
                <FieldLabel htmlFor="invite-role">
                  {t("invitations.role")}
                </FieldLabel>
                <NativeSelect
                  id="invite-role"
                  value={field.value}
                  onBlur={field.onBlur}
                  onChange={(event) => {
                    const next = roles.find(
                      (value) => value === event.target.value
                    )
                    if (next !== undefined) field.onChange(next)
                  }}
                >
                  {roles.map((value) => (
                    <NativeSelectOption key={value} value={value}>
                      {t(`role.${value}`)}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </Field>
            )}
          />
          <Button
            type="submit"
            className="sm:mt-6"
            disabled={form.formState.isSubmitting}
          >
            {t("invitations.invite")}
          </Button>
        </form>
      ) : null}
      {notice === null ? null : (
        <output className="text-sm text-muted-foreground">{notice}</output>
      )}
      {invitations.data === undefined ? (
        <Spinner />
      ) : invitations.data.length === 0 ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyDescription>{t("invitations.empty")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <ItemGroup className="gap-2">
          {invitations.data.map((invitation) => (
            <Item key={invitation.id} variant="outline" size="sm">
              <ItemContent>
                <ItemTitle>
                  {invitation.email}
                  <Badge variant="secondary">
                    {t(`invitations.statusValue.${invitation.status}`)}
                  </Badge>
                </ItemTitle>
                <ItemDescription>
                  {t(`role.${invitation.role}`)} · {invitation.invited_by_name}
                  {invitation.expires_at
                    ? ` · ${t("invitations.expires")} ${format.format(new Date(invitation.expires_at))}`
                    : ""}
                </ItemDescription>
              </ItemContent>
              <ItemActions>{actions(invitation)}</ItemActions>
            </Item>
          ))}
        </ItemGroup>
      )}
    </div>
  )
}
