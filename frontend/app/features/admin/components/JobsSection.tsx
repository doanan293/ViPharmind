import { useTranslation } from "react-i18next"
import { Link } from "react-router"

import {
  useAdminCollectionsList,
  useAdminIngestJobsList,
} from "~/api/gen/endpoints"
import type { JobStatus, JobStep, JobView } from "~/api/gen/schemas"
import { DataTable, dataTableColumns } from "~/components/data-table"
import { Badge } from "~/components/ui/badge"
import { Progress } from "~/components/ui/progress"
import { Spinner } from "~/components/ui/spinner"

import {
  AdminHeader,
  type AdminKey,
  DateCell,
  useColumnLabels,
} from "./columns"

/** How many of the latest ingest jobs the console lists. */
export const RECENT_JOBS = 50
const POLL_MS = 5000
const column = dataTableColumns<JobView>()

const LABELS = {
  collection_id: "jobs.collection",
  status: "jobs.status",
  step: "jobs.step",
  progress: "jobs.progress",
  created_at: "jobs.created",
  error: "jobs.error",
} as const satisfies Record<string, AdminKey>

function StatusCell({ value }: { value: JobStatus }) {
  const { t } = useTranslation("admin")
  return (
    <Badge variant={value === "failed" ? "destructive" : "outline"}>
      {t(`jobs.statusValue.${value}`)}
    </Badge>
  )
}

function StepCell({ value }: { value: JobStep }) {
  const { t } = useTranslation("collections")
  return t(`publish.step.${value}`)
}

function ProgressCell({ value }: { value: number }) {
  const { t } = useTranslation("admin")
  return (
    <Progress value={value} aria-label={t("jobs.progress")} className="w-32" />
  )
}

/** How much of a collection id to show when its title is unknown. */
const SHORT_ID_LENGTH = 8

/** The collection's title (from the console's collection list), else its short id. */
function CollectionCell({ id }: { id: string }) {
  const stats = useAdminCollectionsList()
  const title = stats.data?.find((item) => item.collection.id === id)
    ?.collection.title
  return (
    <Link
      to={`/collections/${id}/releases`}
      className={
        title === undefined
          ? "font-mono text-xs underline-offset-4 hover:underline"
          : "underline-offset-4 hover:underline"
      }
    >
      {title ?? id.slice(0, SHORT_ID_LENGTH)}
    </Link>
  )
}

const COLUMNS = column.columns([
  column.accessor("collection_id", {
    header: () => <AdminHeader k={LABELS.collection_id} />,
    enableHiding: false,
    enableSorting: false,
    cell: ({ getValue }) => <CollectionCell id={getValue()} />,
  }),
  column.accessor("status", {
    header: () => <AdminHeader k={LABELS.status} />,
    cell: ({ getValue }) => <StatusCell value={getValue()} />,
  }),
  column.accessor("step", {
    header: () => <AdminHeader k={LABELS.step} />,
    cell: ({ getValue }) => <StepCell value={getValue()} />,
  }),
  column.accessor("progress", {
    header: () => <AdminHeader k={LABELS.progress} />,
    cell: ({ getValue }) => <ProgressCell value={getValue()} />,
  }),
  column.accessor("created_at", {
    header: () => <AdminHeader k={LABELS.created_at} />,
    cell: ({ getValue }) => <DateCell value={getValue()} time />,
  }),
  column.accessor((row) => row.error ?? "", {
    id: "error",
    header: () => <AdminHeader k={LABELS.error} />,
    enableSorting: false,
    cell: ({ getValue }) => (
      <span className="block max-w-64 truncate text-destructive">
        {getValue()}
      </span>
    ),
  }),
])

/** Recent publish jobs; refreshes while any of them is still queued or running. */
export function JobsSection() {
  const labels = useColumnLabels(LABELS)
  const jobs = useAdminIngestJobsList(
    { limit: RECENT_JOBS },
    {
      query: {
        refetchInterval: (query) =>
          query.state.data?.some(
            (job) => job.status === "queued" || job.status === "running"
          ) === true
            ? POLL_MS
            : false,
      },
    }
  )
  if (jobs.data === undefined) return <Spinner />
  return (
    <DataTable
      data={jobs.data}
      columns={COLUMNS}
      columnLabels={labels}
      getRowId={(job) => job.id}
    />
  )
}
