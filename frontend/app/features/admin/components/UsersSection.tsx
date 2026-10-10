import { keepPreviousData, useQueryClient } from "@tanstack/react-query"
import { SearchIcon } from "lucide-react"
import { createContext, useContext, useDeferredValue, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  getAdminUsersListInfiniteQueryKey,
  useAdminUsersListInfinite,
  useAdminUsersUpdate,
} from "~/api/gen/endpoints"
import type { AdminUserView } from "~/api/gen/schemas"
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
import { DataTable, dataTableColumns } from "~/components/data-table"
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
  type AdminKey,
  AdminHeader,
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

function StatusCell({ active }: { active: boolean }) {
  const { t } = useTranslation("admin")
  return (
    <Badge variant={active ? "outline" : "destructive"}>
      {active ? t("users.active") : t("users.disabled")}
    </Badge>
  )
}

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

export function UsersSection() {
  const { t } = useTranslation("admin")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const q = useDeferredValue(search.trim())
  const params = { limit: 50, ...(q === "" ? {} : { q }) }
  const users = useAdminUsersListInfinite(params, {
    query: {
      initialPageParam: undefined,
      getNextPageParam: (page) => page.next_cursor ?? undefined,
      // The search box lives in the table: keep the table while a new search loads.
      placeholderData: keepPreviousData,
    },
  })
  const update = useAdminUsersUpdate()
  const [dialog, setDialog] = useState<Dialog>(null)
  const labels = useColumnLabels(LABELS)

  const refresh = () =>
    queryClient.invalidateQueries({
      queryKey: getAdminUsersListInfiniteQueryKey(),
    })
  const items = users.data?.pages.flatMap((page) => page.items) ?? []
  const toggling = dialog?.kind === "toggle" ? dialog.user : null

  return (
    <OpenDialog value={setDialog}>
      <div className="flex flex-col gap-4">
        {users.data === undefined ? (
          <Spinner />
        ) : (
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
        )}

        <AlertDialog
          open={toggling !== null}
          onOpenChange={(open) => {
            if (!open) setDialog(null)
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>
                {toggling?.is_active === false
                  ? t("users.enableTitle", { name: toggling.display_name })
                  : t("users.disableTitle", { name: toggling?.display_name })}
              </AlertDialogTitle>
              <AlertDialogDescription>
                {toggling?.is_active === false
                  ? t("users.enableDescription")
                  : t("users.disableDescription")}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
              <Button
                variant={
                  toggling?.is_active === false ? "default" : "destructive"
                }
                disabled={update.isPending}
                onClick={() => {
                  if (toggling === null) return
                  const isActive = !toggling.is_active
                  update.mutate(
                    { userId: toggling.id, data: { is_active: isActive } },
                    {
                      onSuccess: () => {
                        toast.add({
                          type: "success",
                          title: isActive
                            ? t("users.enabledToast", {
                                name: toggling.display_name,
                              })
                            : t("users.disabledToast", {
                                name: toggling.display_name,
                              }),
                        })
                        setDialog(null)
                        void refresh()
                      },
                      onError: (error) =>
                        toast.add({
                          type: "error",
                          title: apiErrorMessage(error, tErrors),
                        }),
                    }
                  )
                }}
              >
                {t("confirm")}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {dialog?.kind === "quota" ? (
          <QuotaDialog
            name={dialog.user.display_name}
            quota={dialog.user}
            open
            onOpenChange={(open) => {
              if (!open) setDialog(null)
            }}
            onSave={async (quota) => {
              await update.mutateAsync({ userId: dialog.user.id, data: quota })
              toast.add({ type: "success", title: t("quota.saved") })
              await refresh()
            }}
          />
        ) : null}

        <UserConversationsSheet
          user={dialog?.kind === "conversations" ? dialog.user : null}
          onClose={() => setDialog(null)}
        />
      </div>
    </OpenDialog>
  )
}
