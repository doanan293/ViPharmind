import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  getCollectionsGetQueryKey,
  getCollectionsReleasesQueryKey,
  useCollectionsPublish,
  useJobsGet,
} from "~/api/gen/endpoints"
import type { JobView } from "~/api/gen/schemas"
import { Button } from "~/components/ui/button"
import { Progress } from "~/components/ui/progress"
import { toast } from "~/components/ui/toast"
import { Alert, AlertDescription } from "~/components/ui/alert"
import { apiErrorMessage } from "~/i18n/error-message"

const POLL_MS = 2000

function finished(job: JobView | undefined): boolean {
  return job?.status === "ready" || job?.status === "failed"
}

function JobProgress({ job }: { job: JobView }) {
  const { t } = useTranslation("collections")
  if (job.status === "ready") {
    return (
      <output className="text-sm">
        {t("publish.ready", { number: job.release_number })}
      </output>
    )
  }
  if (job.status === "failed") {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          {t("publish.failed", { error: job.error ?? "" })}
        </AlertDescription>
      </Alert>
    )
  }
  return (
    <output className="flex min-w-48 flex-col gap-1 text-sm">
      <span>{t(`publish.step.${job.step}`)}</span>
      <Progress value={job.progress} aria-label={t("publish.running")} />
    </output>
  )
}

/** Starts a publish job and follows it until the new release is live. */
export function PublishButton({ collectionId }: { collectionId: string }) {
  const { t } = useTranslation("collections")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const publish = useCollectionsPublish()
  const [jobId, setJobId] = useState<string | null>(null)
  const job = useJobsGet(jobId ?? "", {
    query: {
      enabled: jobId !== null,
      refetchInterval: (query) =>
        finished(query.state.data) ? false : POLL_MS,
    },
  })
  const done = finished(job.data)

  useEffect(() => {
    if (job.data?.status !== "ready") return
    void queryClient.invalidateQueries({
      queryKey: getCollectionsGetQueryKey(collectionId),
    })
    void queryClient.invalidateQueries({
      queryKey: getCollectionsReleasesQueryKey(collectionId),
    })
  }, [job.data?.status, collectionId, queryClient])

  const running = publish.isPending || (jobId !== null && !done)
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        disabled={running}
        onClick={() =>
          publish.mutate(
            { collectionId },
            {
              onSuccess: (started) => setJobId(started.id),
              onError: (error) =>
                toast.add({
                  type: "error",
                  title: apiErrorMessage(error, tErrors),
                }),
            }
          )
        }
      >
        {running ? t("publish.running") : t("publish.button")}
      </Button>
      {job.data === undefined ? null : <JobProgress job={job.data} />}
    </div>
  )
}
