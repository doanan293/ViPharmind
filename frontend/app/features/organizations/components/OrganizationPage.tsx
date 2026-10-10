import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

import {
  getOrganizationsGetQueryKey,
  getOrganizationsListQueryKey,
  useAuditOrganizationInfinite,
  useOrganizationsDelete,
  useOrganizationsGet,
  useOrganizationsLeave,
  useOrganizationsRename,
  useUsersCurrentUser,
} from "~/api/gen/endpoints"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "~/components/ui/alert-dialog"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Input } from "~/components/ui/input"
import { Spinner } from "~/components/ui/spinner"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs"
import { toast } from "~/components/ui/toast"
import { Alert, AlertDescription } from "~/components/ui/alert"
import { AuditList } from "~/features/audit/components/AuditList"
import { apiErrorMessage } from "~/i18n/error-message"

import { type Viewer, atLeast } from "../lib/roles"
import { InvitationsTab } from "./InvitationsTab"
import { MembersTab } from "./MembersTab"
import { OrgCollectionsTab } from "./OrgCollectionsTab"

const TABS = ["members", "invitations", "collections", "audit"] as const
type Tab = (typeof TABS)[number]

function OrganizationLog({ organizationId }: { organizationId: string }) {
  const query = useAuditOrganizationInfinite(
    organizationId,
    { limit: 50 },
    {
      query: {
        initialPageParam: undefined,
        getNextPageParam: (page) => page.next_cursor ?? undefined,
      },
    }
  )
  return <AuditList query={query} />
}

type Confirm = "delete" | "leave" | null

export function OrganizationPage({
  organizationId,
  tab,
}: {
  organizationId: string
  tab: string | undefined
}) {
  const { t } = useTranslation("organizations")
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useUsersCurrentUser()
  const organization = useOrganizationsGet(organizationId)
  const rename = useOrganizationsRename()
  const remove = useOrganizationsDelete()
  const leave = useOrganizationsLeave()
  const [renaming, setRenaming] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<Confirm>(null)
  const [typed, setTyped] = useState("")

  if (organization.isError) {
    return (
      <Alert variant="destructive" className="m-4 w-auto md:m-8">
        <AlertDescription>
          {apiErrorMessage(organization.error, tErrors)}
        </AlertDescription>
      </Alert>
    )
  }
  if (organization.data === undefined || user.data === undefined) {
    return <Spinner />
  }
  const org = organization.data
  const viewer: Viewer = {
    role: org.role ?? null,
    superadmin: user.data.is_superadmin,
  }
  const tabs = TABS.filter(
    (name) => name !== "audit" || atLeast(viewer, "editor")
  )
  const current: Tab = tabs.find((name) => name === tab) ?? "members"
  const fail = (error: unknown) =>
    toast.add({ type: "error", title: apiErrorMessage(error, tErrors) })
  const gone = async () => {
    await queryClient.invalidateQueries({
      queryKey: getOrganizationsListQueryKey(),
    })
    await navigate("/organizations", { replace: true })
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 p-4 md:p-8">
      <title>{org.name}</title>
      <div className="flex flex-wrap items-center justify-between gap-3">
        {renaming === null ? (
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold">{org.name}</h1>
            <Badge variant="secondary">
              {t(`role.${org.role ?? "admin"}`)}
            </Badge>
          </div>
        ) : (
          <form
            className="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              rename.mutate(
                { organizationId, data: { name: renaming.trim() } },
                {
                  onSuccess: (updated) => {
                    queryClient.setQueryData(
                      getOrganizationsGetQueryKey(organizationId),
                      updated
                    )
                    setRenaming(null)
                  },
                  onError: fail,
                }
              )
            }}
          >
            <Input
              aria-label={t("create.name")}
              value={renaming}
              maxLength={100}
              onChange={(event) => setRenaming(event.target.value)}
            />
            <Button type="submit">{t("actions.save")}</Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => setRenaming(null)}
            >
              {t("actions.cancel")}
            </Button>
          </form>
        )}
        <div className="flex gap-2">
          {atLeast(viewer, "owner") && renaming === null ? (
            <>
              <Button variant="outline" onClick={() => setRenaming(org.name)}>
                {t("actions.rename")}
              </Button>
              <Button
                variant="destructive"
                onClick={() => setConfirm("delete")}
              >
                {t("actions.delete")}
              </Button>
            </>
          ) : null}
          {org.role !== null && org.role !== undefined ? (
            <Button variant="outline" onClick={() => setConfirm("leave")}>
              {t("actions.leave")}
            </Button>
          ) : null}
        </div>
      </div>
      <Tabs
        value={current}
        onValueChange={(value) =>
          void navigate(`/organizations/${organizationId}/${String(value)}`)
        }
      >
        <TabsList>
          {tabs.map((name) => (
            <TabsTrigger key={name} value={name}>
              {t(`tabs.${name}`)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="members">
          <MembersTab
            organizationId={organizationId}
            viewer={viewer}
            currentUserId={user.data.id}
          />
        </TabsContent>
        <TabsContent value="invitations">
          <InvitationsTab
            organizationId={organizationId}
            viewer={viewer}
            currentUserId={user.data.id}
          />
        </TabsContent>
        <TabsContent value="collections">
          <OrgCollectionsTab organizationId={organizationId} viewer={viewer} />
        </TabsContent>
        {tabs.includes("audit") ? (
          <TabsContent value="audit">
            <OrganizationLog organizationId={organizationId} />
          </TabsContent>
        ) : null}
      </Tabs>
      <AlertDialog
        open={confirm !== null}
        onOpenChange={(open) => {
          if (!open) {
            setConfirm(null)
            setTyped("")
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirm === "delete" ? t("delete.title") : t("leave.title")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirm === "delete"
                ? t("delete.description", { name: org.name })
                : t("leave.description")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {confirm === "delete" ? (
            <Input
              aria-label={t("create.name")}
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
            />
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel>{t("actions.cancel")}</AlertDialogCancel>
            {confirm === "delete" ? (
              <Button
                variant="destructive"
                disabled={typed.trim() !== org.name || remove.isPending}
                onClick={() =>
                  remove.mutate(
                    { organizationId, data: { confirm_name: typed.trim() } },
                    { onSuccess: () => void gone(), onError: fail }
                  )
                }
              >
                {t("delete.confirm")}
              </Button>
            ) : (
              <Button
                disabled={leave.isPending}
                onClick={() =>
                  leave.mutate(
                    { organizationId },
                    { onSuccess: () => void gone(), onError: fail }
                  )
                }
              >
                {t("leave.confirm")}
              </Button>
            )}
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
