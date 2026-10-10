import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import {
  getAdminOrganizationsListInfiniteQueryKey,
  useAdminOrganizationsListInfinite,
  useAdminOrganizationsUpdate,
} from "~/api/gen/endpoints"
import type { AdminOrganizationView } from "~/api/gen/schemas"
import { Button } from "~/components/ui/button"
import { Empty, EmptyDescription, EmptyHeader } from "~/components/ui/empty"
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

import { QuotaDialog } from "./QuotaDialog"
import { QuotaValue } from "./QuotaValue"

export function OrganizationsSection() {
  const { t, i18n } = useTranslation("admin")
  const queryClient = useQueryClient()
  const organizations = useAdminOrganizationsListInfinite(
    { limit: 50 },
    {
      query: {
        initialPageParam: undefined,
        getNextPageParam: (page) => page.next_cursor ?? undefined,
      },
    }
  )
  const update = useAdminOrganizationsUpdate()
  const [editing, setEditing] = useState<AdminOrganizationView | null>(null)
  const dates = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" })

  if (organizations.data === undefined) return <Spinner />
  const items = organizations.data.pages.flatMap((page) => page.items)
  if (items.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyDescription>{t("organizations.empty")}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }
  return (
    <div className="flex flex-col gap-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("organizations.name")}</TableHead>
            <TableHead className="text-right">
              {t("organizations.members")}
            </TableHead>
            <TableHead>{t("organizations.quota")}</TableHead>
            <TableHead>{t("organizations.created")}</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((organization) => (
            <TableRow key={organization.id}>
              <TableCell className="font-medium">{organization.name}</TableCell>
              <TableCell className="text-right">
                {organization.member_count}
              </TableCell>
              <TableCell>
                <QuotaValue quota={organization} />
              </TableCell>
              <TableCell>
                {dates.format(new Date(organization.created_at))}
              </TableCell>
              <TableCell className="text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setEditing(organization)}
                >
                  {t("organizations.quota")}
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {organizations.hasNextPage ? (
        <Button
          variant="outline"
          className="self-center"
          disabled={organizations.isFetchingNextPage}
          onClick={() => void organizations.fetchNextPage()}
        >
          {t("users.more")}
        </Button>
      ) : null}
      {editing === null ? null : (
        <QuotaDialog
          name={editing.name}
          quota={editing}
          open
          onOpenChange={(open) => {
            if (!open) setEditing(null)
          }}
          onSave={async (quota) => {
            await update.mutateAsync({
              organizationId: editing.id,
              data: quota,
            })
            toast.add({ type: "success", title: t("quota.saved") })
            await queryClient.invalidateQueries({
              queryKey: getAdminOrganizationsListInfiniteQueryKey(),
            })
          }}
        />
      )}
    </div>
  )
}
