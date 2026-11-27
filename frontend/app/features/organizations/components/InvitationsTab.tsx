import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { type Control, Controller, useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import type { z } from "zod"

import {
  getInvitationsListQueryKey,
  useInvitationsApprove,
  useInvitationsCreate,
  useInvitationsList,
  useInvitationsReject,
  useInvitationsResend,
  useInvitationsRevoke,
} from "~/api/gen/endpoints"
import type { InvitationView, Role } from "~/api/gen/schemas"
import { InvitationsCreateBody } from "~/api/gen/zod"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Empty, EmptyDescription, EmptyHeader } from "~/components/ui/empty"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "~/components/ui/item"
import { NativeSelect, NativeSelectOption } from "~/components/ui/native-select"
import { Spinner } from "~/components/ui/spinner"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"

import { atLeast, invitableRoles, type Viewer } from "../lib/roles"

/** Acts on one invitation by id; each action refreshes the list or toasts the error. */
type InvitationActionsApi = Record<
  "approve" | "reject" | "revoke" | "resend",
  (invitationId: string) => void
>

/** The approve, reject, revoke and resend actions for the organization's invitations. */
function useInvitationActions(organizationId: string): InvitationActionsApi {
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const approve = useInvitationsApprove()
  const reject = useInvitationsReject()
  const revoke = useInvitationsRevoke()
  const resend = useInvitationsResend()
  const act = {
    onSuccess: () =>
      void queryClient.invalidateQueries({
        queryKey: getInvitationsListQueryKey(organizationId),
      }),
    onError: (error: unknown) =>
      toast.add({ type: "error", title: apiErrorMessage(error, tErrors) }),
  }
  return {
    approve: (invitationId) =>
      approve.mutate({ organizationId, invitationId }, act),
    reject: (invitationId) =>
      reject.mutate({ organizationId, invitationId }, act),
    revoke: (invitationId) =>
      revoke.mutate({ organizationId, invitationId }, act),
    resend: (invitationId) =>
      resend.mutate({ organizationId, invitationId }, act),
  }
}

/** What the invite form holds; `role` may be missing until zod applies its default. */
type InviteInput = z.input<typeof InvitationsCreateBody>
/** What the invite form submits. */
type InviteValues = z.output<typeof InvitationsCreateBody>

/** The role to invite with, limited to the roles the viewer may grant. */
function InviteRoleField({
  control,
  roles,
}: {
  control: Control<InviteInput, unknown, InviteValues>
  roles: Role[]
}) {
  const { t } = useTranslation("organizations")
  return (
    <Controller
      name="role"
      control={control}
      render={({ field }) => (
        <Field className="sm:w-48">
          <FieldLabel htmlFor="invite-role">{t("invitations.role")}</FieldLabel>
          <NativeSelect
            id="invite-role"
            value={field.value}
            onBlur={field.onBlur}
            onChange={(event) => {
              const next = roles.find((value) => value === event.target.value)
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
  )
}

/** Invites by email with a role the viewer may grant; reports whether it was sent or awaits approval. */
function InviteForm({
  organizationId,
  roles,
  onNotice,
}: {
  organizationId: string
  roles: Role[]
  onNotice: (notice: string) => void
}) {
  const { t } = useTranslation("organizations")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const create = useInvitationsCreate()
  const form = useForm({
    resolver: zodResolver(InvitationsCreateBody),
    defaultValues: { email: "", role: "member" as const },
  })
  const serverError = form.formState.errors.root?.server?.message

  async function onSubmit(data: InviteValues) {
    try {
      const created = await create.mutateAsync({ organizationId, data })
      form.reset({ email: "", role: data.role })
      onNotice(
        created.status === "pending_approval"
          ? t("invitations.pending")
          : t("invitations.sent")
      )
      await queryClient.invalidateQueries({
        queryKey: getInvitationsListQueryKey(organizationId),
      })
    } catch (error) {
      applyApiError(
        error,
        form.setError,
        ["email", "role"],
        apiErrorMessage(error, tErrors)
      )
    }
  }

  return (
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
      <InviteRoleField control={form.control} roles={roles} />
      <Button
        type="submit"
        className="sm:mt-6"
        disabled={form.formState.isSubmitting}
      >
        {t("invitations.invite")}
      </Button>
    </form>
  )
}

/** Who may act on an invitation, and the actions to call. */
type InvitationActionProps = {
  invitation: InvitationView
  canDecide: boolean
  mine: boolean
  actions: InvitationActionsApi
}

/** A pending invitation: editors approve or reject it; its inviter may only revoke it. */
function PendingActions({
  invitation,
  canDecide,
  mine,
  actions,
}: InvitationActionProps) {
  const { t } = useTranslation("organizations")
  if (canDecide) {
    return (
      <>
        <Button size="sm" onClick={() => actions.approve(invitation.id)}>
          {t("invitations.approve")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => actions.reject(invitation.id)}
        >
          {t("invitations.reject")}
        </Button>
      </>
    )
  }
  return mine ? (
    <Button
      size="sm"
      variant="outline"
      onClick={() => actions.revoke(invitation.id)}
    >
      {t("invitations.revoke")}
    </Button>
  ) : null
}

/** The actions an invitation allows in its status, for editors and its inviter. */
function InvitationActions(props: InvitationActionProps) {
  const { t } = useTranslation("organizations")
  const { invitation, canDecide, mine, actions } = props
  if (invitation.status === "pending_approval") {
    return <PendingActions {...props} />
  }
  const resendable =
    invitation.status === "sent" || invitation.status === "expired"
  if (!resendable || !(canDecide || mine)) {
    return null
  }
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        onClick={() => actions.resend(invitation.id)}
      >
        {t("invitations.resend")}
      </Button>
      {invitation.status === "sent" ? (
        <Button
          size="sm"
          variant="outline"
          onClick={() => actions.revoke(invitation.id)}
        >
          {t("invitations.revoke")}
        </Button>
      ) : null}
    </>
  )
}

/** The invitation list, or an empty state when there is none. */
function InvitationList({
  invitations,
  viewer,
  currentUserId,
  actions,
}: {
  invitations: InvitationView[]
  viewer: Viewer
  currentUserId: string
  actions: InvitationActionsApi
}) {
  const { t, i18n } = useTranslation("organizations")
  const canDecide = atLeast(viewer, "editor")
  const format = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" })
  if (invitations.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyDescription>{t("invitations.empty")}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }
  return (
    <ItemGroup className="gap-2">
      {invitations.map((invitation) => (
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
          <ItemActions>
            <InvitationActions
              invitation={invitation}
              canDecide={canDecide}
              mine={invitation.invited_by === currentUserId}
              actions={actions}
            />
          </ItemActions>
        </Item>
      ))}
    </ItemGroup>
  )
}

/** The organization's invitations: the invite form for roles the viewer may grant, and the list. */
export function InvitationsTab({
  organizationId,
  viewer,
  currentUserId,
}: {
  organizationId: string
  viewer: Viewer
  currentUserId: string
}) {
  const invitations = useInvitationsList(organizationId)
  const actions = useInvitationActions(organizationId)
  const roles = invitableRoles(viewer)
  const [notice, setNotice] = useState<string | null>(null)

  return (
    <div className="flex flex-col gap-6">
      {roles.length > 0 ? (
        <InviteForm
          organizationId={organizationId}
          roles={roles}
          onNotice={setNotice}
        />
      ) : null}
      {notice === null ? null : (
        <output className="text-sm text-muted-foreground">{notice}</output>
      )}
      {invitations.data === undefined ? (
        <Spinner />
      ) : (
        <InvitationList
          invitations={invitations.data}
          viewer={viewer}
          currentUserId={currentUserId}
          actions={actions}
        />
      )}
    </div>
  )
}
