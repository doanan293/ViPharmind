import { useQueryClient } from "@tanstack/react-query"
import { SearchIcon } from "lucide-react"
import { useDeferredValue, useState } from "react"
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
import { Button } from "~/components/ui/button"
import { Empty, EmptyDescription, EmptyHeader } from "~/components/ui/empty"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "~/components/ui/input-group"
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

import { QuotaDialog } from "./QuotaDialog"
import { QuotaValue } from "./QuotaValue"
import { UserConversationsSheet } from "./UserConversationsSheet"

type Dialog =
  | { kind: "toggle"; user: AdminUserView }
  | { kind: "quota"; user: AdminUserView }
  | { kind: "conversations"; user: AdminUserView }
  | null

export function UsersSection() {
  const { t, i18n } = useTranslation("admin")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const q = useDeferredValue(search.trim())
  const params = { limit: 50, ...(q === "" ? {} : { q }) }
  const users = useAdminUsersListInfinite(params, {
    query: {
      initialPageParam: undefined,
      getNextPageParam: (page) => page.next_cursor ?? undefined,
    },
  })
  const update = useAdminUsersUpdate()
  const [dialog, setDialog] = useState<Dialog>(null)
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" })

  const refresh = () =>
    queryClient.invalidateQueries({
      queryKey: getAdminUsersListInfiniteQueryKey(),
    })
  const items = users.data?.pages.flatMap((page) => page.items) ?? []
  const toggling = dialog?.kind === "toggle" ? dialog.user : null

  return (
    <div className="flex flex-col gap-4">
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
      {users.data === undefined ? (
        <Spinner />
      ) : items.length === 0 ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyDescription>{t("users.empty")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("users.name")}</TableHead>
              <TableHead>{t("users.status")}</TableHead>
              <TableHead>{t("users.quota")}</TableHead>
              <TableHead>{t("users.created")}</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((user) => (
              <TableRow key={user.id}>
                <TableCell>
                  <div className="flex flex-col">
                    <span className="flex items-center gap-2 font-medium">
                      {user.display_name}
                      {user.is_superadmin ? (
                        <Badge variant="secondary">
                          {t("users.superadmin")}
                        </Badge>
                      ) : null}
                    </span>
                    <span className="text-muted-foreground">
                      {user.email ?? user.phone_number}
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant={user.is_active ? "outline" : "destructive"}>
                    {user.is_active ? t("users.active") : t("users.disabled")}
                  </Badge>
                </TableCell>
                <TableCell>
                  <QuotaValue quota={user} />
                </TableCell>
                <TableCell>
                  {user.created_at === null
                    ? ""
                    : dates.format(new Date(user.created_at))}
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setDialog({ kind: "conversations", user })}
                    >
                      {t("users.conversations")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setDialog({ kind: "quota", user })}
                    >
                      {t("users.quota")}
                    </Button>
                    <Button
                      variant={user.is_active ? "ghost" : "outline"}
                      size="sm"
                      onClick={() => setDialog({ kind: "toggle", user })}
                    >
                      {user.is_active ? t("users.disable") : t("users.enable")}
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {users.hasNextPage ? (
        <Button
          variant="outline"
          className="self-center"
          disabled={users.isFetchingNextPage}
          onClick={() => void users.fetchNextPage()}
        >
          {t("users.more")}
        </Button>
      ) : null}

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
  )
}
