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
import type { OrganizationView } from "~/api/gen/schemas"
import { NameForm } from "~/components/name-form"
import { Alert, AlertDescription } from "~/components/ui/alert"
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
import { AuditList } from "~/features/audit/components/AuditList"
import { apiErrorMessage } from "~/i18n/error-message"

import { atLeast, type Viewer } from "../lib/roles"
import { InvitationsTab } from "./InvitationsTab"
import { MembersTab } from "./MembersTab"
import { OrgCollectionsTab } from "./OrgCollectionsTab"

const TABS = ["members", "invitations", "collections", "audit"] as const
type Tab = (typeof TABS)[number]

/** The organization's audit log, shown to editors and above. */
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

/** The name with the viewer's role badge, or the rename form while renaming. */
function OrganizationTitle({
  organizationId,
  org,
  renaming,
  onDone,
}: {
  organizationId: string
  org: OrganizationView
  renaming: boolean
  onDone: () => void
}) {
  const { t } = useTranslation("organizations")
  const queryClient = useQueryClient()
  const rename = useOrganizationsRename()
  if (!renaming) {
    return (
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold">{org.name}</h1>
        <Badge variant="secondary">{t(`role.${org.role ?? "admin"}`)}</Badge>
      </div>
    )
  }
  return (
    <NameForm
      id="organization-rename"
      field="name"
      label={t("create.name")}
      hideLabel
      defaultValue={org.name}
      submitLabel={t("actions.save")}
      cancelLabel={t("actions.cancel")}
      requiredMessage={t("create.nameRequired")}
      maxLength={100}
      onCancel={onDone}
      onSubmit={async (name) => {
        const updated = await rename.mutateAsync({
          organizationId,
          data: { name },
        })
        queryClient.setQueryData(
          getOrganizationsGetQueryKey(organizationId),
          updated
        )
        onDone()
      }}
    />
  )
}

/** The title row: name or rename form, and the rename, delete and leave actions. */
function OrganizationHeader({
  organizationId,
  org,
  viewer,
  onConfirm,
}: {
  organizationId: string
  org: OrganizationView
  viewer: Viewer
  onConfirm: (confirm: Confirm) => void
}) {
  const { t } = useTranslation("organizations")
  const [renaming, setRenaming] = useState(false)
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <OrganizationTitle
        organizationId={organizationId}
        org={org}
        renaming={renaming}
        onDone={() => setRenaming(false)}
      />
      <div className="flex gap-2">
        {atLeast(viewer, "owner") && !renaming ? (
          <>
            <Button variant="outline" onClick={() => setRenaming(true)}>
              {t("actions.rename")}
            </Button>
            <Button variant="destructive" onClick={() => onConfirm("delete")}>
              {t("actions.delete")}
            </Button>
          </>
        ) : null}
        {org.role !== null && org.role !== undefined ? (
          <Button variant="outline" onClick={() => onConfirm("leave")}>
            {t("actions.leave")}
          </Button>
        ) : null}
      </div>
    </div>
  )
}

/** The members, invitations, collections and (for editors) audit tabs; a tab is a URL. */
function OrganizationTabs({
  organizationId,
  viewer,
  currentUserId,
  tab,
}: {
  organizationId: string
  viewer: Viewer
  currentUserId: string
  tab: string | undefined
}) {
  const { t } = useTranslation("organizations")
  const navigate = useNavigate()
  const tabs = TABS.filter(
    (name) => name !== "audit" || atLeast(viewer, "editor")
  )
  const current: Tab = tabs.find((name) => name === tab) ?? "members"
  return (
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
          currentUserId={currentUserId}
        />
      </TabsContent>
      <TabsContent value="invitations">
        <InvitationsTab
          organizationId={organizationId}
          viewer={viewer}
          currentUserId={currentUserId}
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
  )
}

/** The confirm button: delete needs the typed name to match, leave needs nothing. */
function ConfirmAction({
  organizationId,
  confirm,
  org,
  typed,
}: {
  organizationId: string
  confirm: Confirm
  org: OrganizationView
  typed: string
}) {
  const { t } = useTranslation("organizations")
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const remove = useOrganizationsDelete()
  const leave = useOrganizationsLeave()
  const fail = (error: unknown) =>
    toast.add({ type: "error", title: apiErrorMessage(error, tErrors) })
  const gone = async () => {
    await queryClient.invalidateQueries({
      queryKey: getOrganizationsListQueryKey(),
    })
    await navigate("/organizations", { replace: true })
  }
  if (confirm === "delete") {
    return (
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
    )
  }
  return (
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
  )
}

/** Confirms deleting (by typing the name) or leaving the organization. */
function ConfirmDialog({
  organizationId,
  confirm,
  org,
  onClose,
}: {
  organizationId: string
  confirm: Confirm
  org: OrganizationView
  onClose: () => void
}) {
  const { t } = useTranslation("organizations")
  const [typed, setTyped] = useState("")
  const isDelete = confirm === "delete"
  return (
    <AlertDialog
      open={confirm !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose()
          setTyped("")
        }
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {isDelete ? t("delete.title") : t("leave.title")}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {isDelete
              ? t("delete.description", { name: org.name })
              : t("leave.description")}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {isDelete ? (
          <Input
            aria-label={t("create.name")}
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
          />
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel>{t("actions.cancel")}</AlertDialogCancel>
          <ConfirmAction
            organizationId={organizationId}
            confirm={confirm}
            org={org}
            typed={typed}
          />
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/** One organization: header actions, its tabs and the delete or leave confirmation. */
export function OrganizationPage({
  organizationId,
  tab,
}: {
  organizationId: string
  tab: string | undefined
}) {
  const { t: tErrors } = useTranslation("errors")
  const user = useUsersCurrentUser()
  const organization = useOrganizationsGet(organizationId)
  const [confirm, setConfirm] = useState<Confirm>(null)

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

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 p-4 md:p-8">
      <title>{org.name}</title>
      <OrganizationHeader
        organizationId={organizationId}
        org={org}
        viewer={viewer}
        onConfirm={setConfirm}
      />
      <OrganizationTabs
        organizationId={organizationId}
        viewer={viewer}
        currentUserId={user.data.id}
        tab={tab}
      />
      <ConfirmDialog
        organizationId={organizationId}
        confirm={confirm}
        org={org}
        onClose={() => setConfirm(null)}
      />
    </div>
  )
}
