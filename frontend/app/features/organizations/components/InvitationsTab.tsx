import { useQueryClient } from "@tanstack/react-query"
import { type FormEvent, useState } from "react"
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
import type { InvitationView, Role } from "~/api/gen/schemas"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Field, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { NativeSelect, NativeSelectOption } from "~/components/ui/native-select"
import { Spinner } from "~/components/ui/spinner"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"

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
  const [email, setEmail] = useState("")
  const [role, setRole] = useState<Role>("member")
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

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    create.mutate(
      { organizationId, data: { email: email.trim(), role } },
      {
        onSuccess: (created) => {
          setEmail("")
          setNotice(
            created.status === "pending_approval"
              ? t("invitations.pending")
              : t("invitations.sent")
          )
          void refresh()
        },
        onError: fail,
      }
    )
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
          onSubmit={submit}
          className="flex flex-col gap-3 sm:flex-row sm:items-end"
        >
          <Field className="flex-1">
            <FieldLabel htmlFor="invite-email">
              {t("invitations.email")}
            </FieldLabel>
            <Input
              id="invite-email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>
          <Field className="sm:w-48">
            <FieldLabel htmlFor="invite-role">
              {t("invitations.role")}
            </FieldLabel>
            <NativeSelect
              id="invite-role"
              value={role}
              onChange={(event) => {
                const next = roles.find((value) => value === event.target.value)
                if (next !== undefined) setRole(next)
              }}
            >
              {roles.map((value) => (
                <NativeSelectOption key={value} value={value}>
                  {t(`role.${value}`)}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Field>
          <Button
            type="submit"
            disabled={create.isPending || email.trim() === ""}
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
        <p className="text-sm text-muted-foreground">
          {t("invitations.empty")}
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {invitations.data.map((invitation) => (
            <li
              key={invitation.id}
              className="flex flex-wrap items-center justify-between gap-2 text-sm"
            >
              <div className="flex flex-col">
                <span className="flex items-center gap-2">
                  {invitation.email}
                  <Badge variant="secondary">
                    {t(`invitations.statusValue.${invitation.status}`)}
                  </Badge>
                </span>
                <span className="text-muted-foreground">
                  {t(`role.${invitation.role}`)} · {invitation.invited_by_name}
                  {invitation.expires_at
                    ? ` · ${t("invitations.expires")} ${format.format(new Date(invitation.expires_at))}`
                    : ""}
                </span>
              </div>
              <div className="flex gap-2">{actions(invitation)}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
