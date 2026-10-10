import { useTranslation } from "react-i18next"
import { Link } from "react-router"

import { useAdminIngestJobsList } from "~/api/gen/endpoints"
import { Badge } from "~/components/ui/badge"
import { Empty, EmptyDescription, EmptyHeader } from "~/components/ui/empty"
import { Progress } from "~/components/ui/progress"
import { Spinner } from "~/components/ui/spinner"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"

const POLL_MS = 5000

/** Recent publish jobs; refreshes while any of them is still queued or running. */
export function JobsSection() {
  const { t, i18n } = useTranslation("admin")
  const { t: tCollections } = useTranslation("collections")
  const jobs = useAdminIngestJobsList(
    { limit: 50 },
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
  const dates = new Intl.DateTimeFormat(i18n.language, {
    dateStyle: "short",
    timeStyle: "short",
  })
  if (jobs.data === undefined) return <Spinner />
  if (jobs.data.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyDescription>{t("jobs.empty")}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("jobs.collection")}</TableHead>
          <TableHead>{t("jobs.status")}</TableHead>
          <TableHead>{t("jobs.step")}</TableHead>
          <TableHead>{t("jobs.progress")}</TableHead>
          <TableHead>{t("jobs.created")}</TableHead>
          <TableHead>{t("jobs.error")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.data.map((job) => (
          <TableRow key={job.id}>
            <TableCell>
              <Link
                to={`/collections/${job.collection_id}/releases`}
                className="font-mono text-xs underline-offset-4 hover:underline"
              >
                {job.collection_id.slice(0, 8)}
              </Link>
            </TableCell>
            <TableCell>
              <Badge
                variant={job.status === "failed" ? "destructive" : "outline"}
              >
                {t(`jobs.statusValue.${job.status}`)}
              </Badge>
            </TableCell>
            <TableCell>{tCollections(`publish.step.${job.step}`)}</TableCell>
            <TableCell className="w-40">
              <Progress value={job.progress} aria-label={t("jobs.progress")} />
            </TableCell>
            <TableCell>{dates.format(new Date(job.created_at))}</TableCell>
            <TableCell className="max-w-64 truncate text-destructive">
              {job.error ?? ""}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
