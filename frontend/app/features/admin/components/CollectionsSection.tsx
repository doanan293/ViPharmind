import { useTranslation } from "react-i18next"
import { Link } from "react-router"

import { useAdminCollectionsList } from "~/api/gen/endpoints"
import type { CollectionStats, Visibility } from "~/api/gen/schemas"
import { DataTable, dataTableColumns } from "~/components/data-table"
import { Badge } from "~/components/ui/badge"
import { Spinner } from "~/components/ui/spinner"

import {
  type AdminKey,
  AdminHeader,
  NumberCell,
  useColumnLabels,
} from "./columns"

const column = dataTableColumns<CollectionStats>()

const LABELS = {
  title: "collections.title",
  owner: "collections.owner",
  visibility: "collections.visibility",
  documents: "collections.documents",
  qdrant_points: "collections.points",
  release: "collections.release",
} as const satisfies Record<string, AdminKey>

function VisibilityCell({ value }: { value: Visibility }) {
  const { t } = useTranslation("collections")
  return <Badge variant="outline">{t(`visibility.${value}`)}</Badge>
}

const COLUMNS = column.columns([
  column.accessor((row) => row.collection.title, {
    id: "title",
    header: () => <AdminHeader k={LABELS.title} />,
    enableHiding: false,
    cell: ({ row }) => (
      <Link
        to={`/collections/${row.original.collection.id}`}
        className="font-medium underline-offset-4 hover:underline"
      >
        {row.original.collection.title}
      </Link>
    ),
  }),
  column.accessor((row) => row.collection.owner_name, {
    id: "owner",
    header: () => <AdminHeader k={LABELS.owner} />,
  }),
  column.accessor((row) => row.collection.visibility, {
    id: "visibility",
    header: () => <AdminHeader k={LABELS.visibility} />,
    cell: ({ getValue }) => <VisibilityCell value={getValue()} />,
  }),
  column.accessor("documents", {
    header: () => <AdminHeader k={LABELS.documents} />,
    cell: ({ getValue }) => <NumberCell value={getValue()} />,
  }),
  column.accessor("qdrant_points", {
    header: () => <AdminHeader k={LABELS.qdrant_points} />,
    cell: ({ getValue }) => <NumberCell value={getValue()} />,
  }),
  column.accessor((row) => row.collection.current_release_number ?? 0, {
    id: "release",
    header: () => <AdminHeader k={LABELS.release} />,
    cell: ({ getValue }) => getValue() || "—",
  }),
])

/** Every collection with its size in Postgres and Qdrant, to spot drift and heavy users. */
export function CollectionsSection() {
  const stats = useAdminCollectionsList()
  const labels = useColumnLabels(LABELS)
  if (stats.data === undefined) return <Spinner />
  return (
    <DataTable
      data={stats.data}
      columns={COLUMNS}
      columnLabels={labels}
      getRowId={(row) => row.collection.id}
    />
  )
}
