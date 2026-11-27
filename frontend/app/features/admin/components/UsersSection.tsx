import {
  type InfiniteData,
  keepPreviousData,
  useQueryClient,
} from "@tanstack/react-query"
import { SearchIcon } from "lucide-react"
import { createContext, useContext, useDeferredValue, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  getAdminUsersListInfiniteQueryKey,
  useAdminUsersListInfinite,
  useAdminUsersUpdate,
} from "~/api/gen/endpoints"
import type { AdminUserPage, AdminUserView } from "~/api/gen/schemas"
import { DataTable, dataTableColumns } from "~/components/data-table"
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
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "~/components/ui/input-group"
import { Spinner } from "~/components/ui/spinner"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"

import {
  AdminHeader,
  type AdminKey,
  DateCell,
  useColumnLabels,
} from "./columns"
import { QuotaDialog } from "./QuotaDialog"
import { QuotaValue } from "./QuotaValue"
import { UserConversationsSheet } from "./UserConversationsSheet"

type Dialog =
  | { kind: "toggle"; user: AdminUserView }
  | { kind: "quota"; user: AdminUserView }
  | { kind: "conversations"; user: AdminUserView }
  | null

const column = dataTableColumns<AdminUserView>()

const LABELS = {
  display_name: "users.name",
  is_active: "users.status",
  quota: "users.quota",
  created: "users.created",
} as const satisfies Record<string, AdminKey>

/** Opens a dialog for a row; provided by UsersSection, used by the actions cell. */
const OpenDialog = createContext<(dialog: Dialog) => void>(() => undefined)

/** The user's name with a superadmin badge, and their email or phone below. */
function NameCell({ user }: { user: AdminUserView }) {
  const { t } = useTranslation("admin")
  return (
    <div className="flex flex-col">
      <span className="flex items-center gap-2 font-medium">
        {user.display_name}
        {user.is_superadmin ? (
          <Badge variant="secondary">{t("users.superadmin")}</Badge>
        ) : null}
      </span>
      <span className="text-muted-foreground">
        {user.email ?? user.phone_number}
      </span>
    </div>
  )
}

/** Whether the account is active or disabled. */
function StatusCell({ active }: { active: boolean }) {
  const { t } = useTranslation("admin")
  return (
    <Badge variant={active ? "outline" : "destructive"}>
      {active ? t("users.active") : t("users.disabled")}
    </Badge>
  )
}

/** Row buttons that open the conversations, quota or enable/disable dialog. */
function ActionsCell({ user }: { user: AdminUserView }) {
  const { t } = useTranslation("admin")
  const open = useContext(OpenDialog)
  return (
    <div className="flex justify-end gap-1">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => open({ kind: "conversations", user })}
      >
        {t("users.conversations")}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => open({ kind: "quota", user })}
      >
        {t("users.quota")}
      </Button>
      <Button
        variant={user.is_active ? "ghost" : "outline"}
        size="sm"
        onClick={() => open({ kind: "toggle", user })}
      >
        {user.is_active ? t("users.disable") : t("users.enable")}
      </Button>
    </div>
  )
}

const COLUMNS = column.columns([
  column.accessor("display_name", {
    header: () => <AdminHeader k={LABELS.display_name} />,
    enableHiding: false,
    cell: ({ row }) => <NameCell user={row.original} />,
  }),
  column.accessor("is_active", {
    header: () => <AdminHeader k={LABELS.is_active} />,
    cell: ({ getValue }) => <StatusCell active={getValue()} />,
  }),
  column.display({
    id: "quota",
    header: () => <AdminHeader k={LABELS.quota} />,
    cell: ({ row }) => <QuotaValue quota={row.original} />,
  }),
  column.accessor((user) => user.created_at ?? "", {
    id: "created",
    header: () => <AdminHeader k={LABELS.created} />,
    cell: ({ getValue }) => <DateCell value={getValue()} />,
  }),
  column.display({
    id: "actions",
    enableHiding: false,
    cell: ({ row }) => <ActionsCell user={row.original} />,
  }),
])

/** Users shown per page of the list. */
const PAGE_SIZE = 50

/** Every loaded user, or undefined until the first page arrives. */
function usersOf(
  data: InfiniteData<AdminUserPage, unknown> | undefined
): AdminUserView[] | undefined {
  return data?.pages.flatMap((page) => page.items)
}

/** The user list filtered by `search`, a page at a time. */
function useUsers(search: string) {
  const q = useDeferredValue(search.trim())
  const params = { limit: PAGE_SIZE, ...(q === "" ? {} : { q }) }
  return useAdminUsersListInfinite(params, {
    query: {
      initialPageParam: undefined,
      getNextPageParam: (page) => page.next_cursor ?? undefined,
      // The search box lives in the table: keep the table while a new search loads.
      placeholderData: keepPreviousData,
    },
  })
}

/** Refetches every page of the user list. */
function useRefreshUsers() {
  const queryClient = useQueryClient()
  return () =>
    queryClient.invalidateQueries({
      queryKey: getAdminUsersListInfiniteQueryKey(),
    })
}

/** Confirms disabling or enabling `user`; null keeps the dialog closed. */
function ToggleUserDialog({
  user,
  onClose,
}: {
  user: AdminUserView | null
  onClose: () => void
}) {
  const { t } = useTranslation("admin")
  const { t: tErrors } = useTranslation("errors")
  const update = useAdminUsersUpdate()
  const refresh = useRefreshUsers()
  const enabling = user?.is_active === false

  function confirm(target: AdminUserView) {
    const isActive = !target.is_active
    const name = target.display_name
    update.mutate(
      { userId: target.id, data: { is_active: isActive } },
      {
        onSuccess: () => {
          toast.add({
            type: "success",
            title: isActive
              ? t("users.enabledToast", { name })
              : t("users.disabledToast", { name }),
          })
          onClose()
          void refresh()
        },
        onError: (error) =>
          toast.add({ type: "error", title: apiErrorMessage(error, tErrors) }),
      }
    )
  }

  return (
    <AlertDialog
      open={user !== null}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {enabling
              ? t("users.enableTitle", { name: user.display_name })
              : t("users.disableTitle", { name: user?.display_name })}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {enabling
              ? t("users.enableDescription")
              : t("users.disableDescription")}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
          <Button
            variant={enabling ? "default" : "destructive"}
            disabled={update.isPending}
            onClick={() => {
              if (user === null) return
              confirm(user)
            }}
          >
            {t("confirm")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/** Edits the quota of `user`, refreshing the list once saved. */
function UserQuotaDialog({
  user,
  onClose,
}: {
  user: AdminUserView
  onClose: () => void
}) {
  const { t } = useTranslation("admin")
  const update = useAdminUsersUpdate()
  const refresh = useRefreshUsers()
  return (
    <QuotaDialog
      name={user.display_name}
      quota={user}
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      onSave={async (quota) => {
        await update.mutateAsync({ userId: user.id, data: quota })
        toast.add({ type: "success", title: t("quota.saved") })
        await refresh()
      }}
    />
  )
}

/** The searchable user table, with a button to load more. */
function UsersTable() {
  const { t } = useTranslation("admin")
  const [search, setSearch] = useState("")
  const users = useUsers(search)
  const labels = useColumnLabels(LABELS)
  const items = usersOf(users.data)

  if (items === undefined) {
    return <Spinner />
  }
  return (
    <DataTable
      data={items}
      columns={COLUMNS}
      columnLabels={labels}
      getRowId={(user) => user.id}
      toolbar={
        <InputGroup className="max-w-md">
          <InputGroupAddon>
            <SearchIcon aria-hidden />
          </InputGroupAddon>
          <InputGroupInput
            type="search"
            aria-label={t("users.search")}
            placeholder={t("users.search")}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </InputGroup>
      }
      footer={
        users.hasNextPage ? (
          <Button
            variant="outline"
            className="self-center"
            disabled={users.isFetchingNextPage}
            onClick={() => void users.fetchNextPage()}
          >
            {t("users.more")}
          </Button>
        ) : null
      }
    />
  )
}

/** The admin user list: search, disable or enable, quotas, and read-only conversations. */
export function UsersSection() {
  const [dialog, setDialog] = useState<Dialog>(null)
  const close = () => setDialog(null)

  return (
    <OpenDialog value={setDialog}>
      <div className="flex flex-col gap-4">
        <UsersTable />
        <ToggleUserDialog
          user={dialog?.kind === "toggle" ? dialog.user : null}
          onClose={close}
        />
        {dialog?.kind === "quota" ? (
          <UserQuotaDialog user={dialog.user} onClose={close} />
        ) : null}
        <UserConversationsSheet
          user={dialog?.kind === "conversations" ? dialog.user : null}
          onClose={close}
        />
      </div>
    </OpenDialog>
  )
}
