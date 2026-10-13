import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import {
  getOrganizationsMembersListQueryKey,
  useOrganizationsMembersList,
  useOrganizationsMembersRemove,
  useOrganizationsMembersSetRole,
} from "~/api/gen/endpoints"
import { Role } from "~/api/gen/schemas"
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

import { type Viewer, atLeast } from "../lib/roles"

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
  const [removing, setRemoving] = useState<{
    userId: string
    name: string
  } | null>(null)
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
          {members.data.map((member) => {
            const name = member.display_name || member.email || member.user_id
            const isMe = member.user_id === currentUserId
            return (
              <TableRow key={member.user_id}>
                <TableCell>
                  {name}
                  {isMe ? ` (${t("members.you")})` : ""}
                </TableCell>
                <TableCell>{member.email ?? ""}</TableCell>
                <TableCell>
                  {canManage ? (
                    <NativeSelect
                      aria-label={t("members.roleOf", { name })}
                      value={member.role}
                      onChange={(event) => {
                        const role = Object.values(Role).find(
                          (value) => value === event.target.value
                        )
                        if (role === undefined) return
                        setRole.mutate(
                          {
                            organizationId,
                            userId: member.user_id,
                            data: { role },
                          },
                          { onSuccess: () => void refresh(), onError: fail }
                        )
                      }}
                    >
                      {Object.values(Role).map((role) => (
                        <NativeSelectOption key={role} value={role}>
                          {t(`role.${role}`)}
                        </NativeSelectOption>
                      ))}
                    </NativeSelect>
                  ) : (
                    t(`role.${member.role}`)
                  )}
                </TableCell>
                {canManage ? (
                  <TableCell>
                    {isMe ? null : (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          setRemoving({ userId: member.user_id, name })
                        }
                      >
                        {t("members.remove", { name })}
                      </Button>
                    )}
                  </TableCell>
                ) : null}
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
      <AlertDialog
        open={removing !== null}
        onOpenChange={(open) => {
          if (!open) setRemoving(null)
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
              disabled={remove.isPending}
              onClick={() => {
                if (removing === null) return
                remove.mutate(
                  { organizationId, userId: removing.userId },
                  {
                    onSuccess: () => {
                      setRemoving(null)
                      void refresh()
                    },
                    onError: fail,
                  }
                )
              }}
            >
              {t("members.removeConfirm")}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
