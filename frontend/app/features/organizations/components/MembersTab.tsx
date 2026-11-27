import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import {
  getOrganizationsMembersListQueryKey,
  useOrganizationsMembersList,
  useOrganizationsMembersRemove,
  useOrganizationsMembersSetRole,
} from "~/api/gen/endpoints"
import { type MemberItem, Role } from "~/api/gen/schemas"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "~/components/ui/alert-dialog"
import { Button } from "~/components/ui/button"
import { NativeSelect, NativeSelectOption } from "~/components/ui/native-select"
import { Spinner } from "~/components/ui/spinner"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"

import { atLeast, type Viewer } from "../lib/roles"

type Removing = { userId: string; name: string }

/** The member's role: a select for owners, plain text for everyone else. */
function MemberRole({
  member,
  name,
  canManage,
  onChange,
}: {
  member: MemberItem
  name: string
  canManage: boolean
  onChange: (role: Role) => void
}) {
  const { t } = useTranslation("organizations")
  if (!canManage) {
    return t(`role.${member.role}`)
  }
  return (
    <NativeSelect
      aria-label={t("members.roleOf", { name })}
      value={member.role}
      onChange={(event) => {
        const role = Object.values(Role).find(
          (value) => value === event.target.value
        )
        if (role === undefined) return
        onChange(role)
      }}
    >
      {Object.values(Role).map((role) => (
        <NativeSelectOption key={role} value={role}>
          {t(`role.${role}`)}
        </NativeSelectOption>
      ))}
    </NativeSelect>
  )
}

/** One member row; owners can change the role or remove anyone but themselves. */
function MemberRow({
  member,
  isMe,
  canManage,
  onRoleChange,
  onRemove,
}: {
  member: MemberItem
  isMe: boolean
  canManage: boolean
  onRoleChange: (role: Role) => void
  onRemove: (removing: Removing) => void
}) {
  const { t } = useTranslation("organizations")
  const name = member.display_name || member.email || member.user_id
  return (
    <TableRow>
      <TableCell>
        {name}
        {isMe ? ` (${t("members.you")})` : ""}
      </TableCell>
      <TableCell>{member.email ?? ""}</TableCell>
      <TableCell>
        <MemberRole
          member={member}
          name={name}
          canManage={canManage}
          onChange={onRoleChange}
        />
      </TableCell>
      {canManage ? (
        <TableCell>
          {isMe ? null : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onRemove({ userId: member.user_id, name })}
            >
              {t("members.remove", { name })}
            </Button>
          )}
        </TableCell>
      ) : null}
    </TableRow>
  )
}

/** Asks before removing a member; `removing` null keeps the dialog closed. */
function RemoveMemberDialog({
  removing,
  pending,
  onClose,
  onConfirm,
}: {
  removing: Removing | null
  pending: boolean
  onClose: () => void
  onConfirm: (removing: Removing) => void
}) {
  const { t } = useTranslation("organizations")
  return (
    <AlertDialog
      open={removing !== null}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("members.removeTitle")}</AlertDialogTitle>
          <AlertDialogDescription>
            {t("members.removeDescription", { name: removing?.name ?? "" })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("actions.cancel")}</AlertDialogCancel>
          <Button
            variant="destructive"
            disabled={pending}
            onClick={() => {
              if (removing === null) return
              onConfirm(removing)
            }}
          >
            {t("members.removeConfirm")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/** The organization's members with their roles; owners manage roles and membership. */
export function MembersTab({
  organizationId,
  viewer,
  currentUserId,
}: {
  organizationId: string
  viewer: Viewer
  currentUserId: string
}) {
  const { t } = useTranslation("organizations")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const members = useOrganizationsMembersList(organizationId)
  const setRole = useOrganizationsMembersSetRole()
  const remove = useOrganizationsMembersRemove()
  const canManage = atLeast(viewer, "owner")
  const [removing, setRemoving] = useState<Removing | null>(null)
  const refresh = () =>
    queryClient.invalidateQueries({
      queryKey: getOrganizationsMembersListQueryKey(organizationId),
    })
  const fail = (error: unknown) =>
    toast.add({ type: "error", title: apiErrorMessage(error, tErrors) })

  if (members.data === undefined) {
    return <Spinner />
  }
  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("members.name")}</TableHead>
            <TableHead>{t("members.email")}</TableHead>
            <TableHead>{t("members.role")}</TableHead>
            {canManage ? <TableHead /> : null}
          </TableRow>
        </TableHeader>
        <TableBody>
          {members.data.map((member) => (
            <MemberRow
              key={member.user_id}
              member={member}
              isMe={member.user_id === currentUserId}
              canManage={canManage}
              onRoleChange={(role) =>
                setRole.mutate(
                  { organizationId, userId: member.user_id, data: { role } },
                  { onSuccess: () => void refresh(), onError: fail }
                )
              }
              onRemove={setRemoving}
            />
          ))}
        </TableBody>
      </Table>
      <RemoveMemberDialog
        removing={removing}
        pending={remove.isPending}
        onClose={() => setRemoving(null)}
        onConfirm={(target) =>
          remove.mutate(
            { organizationId, userId: target.userId },
            {
              onSuccess: () => {
                setRemoving(null)
                void refresh()
              },
              onError: fail,
            }
          )
        }
      />
    </>
  )
}
