import { useQueryClient } from "@tanstack/react-query"
import { createContext, useContext, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  getAdminOrganizationsListInfiniteQueryKey,
  useAdminOrganizationsListInfinite,
  useAdminOrganizationsUpdate,
} from "~/api/gen/endpoints"
import type { AdminOrganizationView } from "~/api/gen/schemas"
import { DataTable, dataTableColumns } from "~/components/data-table"
import { Button } from "~/components/ui/button"
import { Spinner } from "~/components/ui/spinner"
import { toast } from "~/components/ui/toast"

import {
  type AdminKey,
  AdminHeader,
  DateCell,
  useColumnLabels,
} from "./columns"
import { QuotaDialog } from "./QuotaDialog"
import { QuotaValue } from "./QuotaValue"

const column = dataTableColumns<AdminOrganizationView>()

const LABELS = {
  name: "organizations.name",
  member_count: "organizations.members",
  quota: "organizations.quota",
  created_at: "organizations.created",
} as const satisfies Record<string, AdminKey>

/** Opens the quota dialog for a row; provided by OrganizationsSection. */
const EditQuota = createContext<(organization: AdminOrganizationView) => void>(
  () => undefined
)

function QuotaButton({
  organization,
}: {
  organization: AdminOrganizationView
}) {
  const { t } = useTranslation("admin")
  const edit = useContext(EditQuota)
  return (
    <div className="flex justify-end">
      <Button variant="ghost" size="sm" onClick={() => edit(organization)}>
        {t("organizations.quota")}
      </Button>
    </div>
  )
}

const COLUMNS = column.columns([
  column.accessor("name", {
    header: () => <AdminHeader k={LABELS.name} />,
    enableHiding: false,
    cell: ({ getValue }) => <span className="font-medium">{getValue()}</span>,
  }),
  column.accessor("member_count", {
    header: () => <AdminHeader k={LABELS.member_count} />,
  }),
  column.display({
    id: "quota",
    header: () => <AdminHeader k={LABELS.quota} />,
    cell: ({ row }) => <QuotaValue quota={row.original} />,
  }),
  column.accessor("created_at", {
    header: () => <AdminHeader k={LABELS.created_at} />,
    cell: ({ getValue }) => <DateCell value={getValue()} />,
  }),
  column.display({
    id: "actions",
    enableHiding: false,
    cell: ({ row }) => <QuotaButton organization={row.original} />,
  }),
])

export function OrganizationsSection() {
  const { t } = useTranslation("admin")
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
  const labels = useColumnLabels(LABELS)

  if (organizations.data === undefined) return <Spinner />
  const items = organizations.data.pages.flatMap((page) => page.items)
  return (
    <EditQuota value={setEditing}>
      <div className="flex flex-col gap-4">
        <DataTable
          data={items}
          columns={COLUMNS}
          columnLabels={labels}
          getRowId={(organization) => organization.id}
        />
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
    </EditQuota>
  )
}
