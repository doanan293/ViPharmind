import { useTranslation } from "react-i18next"

import {
  useAdminCollectionsList,
  useAdminIngestJobsList,
} from "~/api/gen/endpoints"
import { SectionCards } from "~/components/section-cards"

import { RECENT_JOBS } from "./JobsSection"

/** The section cards of the dashboard, filled from the admin endpoints. */
export function AdminOverview() {
  const { t, i18n } = useTranslation("admin", { keyPrefix: "overview" })
  const numbers = new Intl.NumberFormat(i18n.language)
  const collections = useAdminCollectionsList().data
  const jobs = useAdminIngestJobsList({ limit: RECENT_JOBS }).data
  const total = (pick: (documents: number, points: number) => number) =>
    collections === undefined
      ? null
      : numbers.format(
          collections.reduce(
            (sum, item) => sum + pick(item.documents, item.qdrant_points),
            0
          )
        )
  return (
    <SectionCards
      cards={[
        {
          label: t("collections"),
          value:
            collections === undefined
              ? null
              : numbers.format(collections.length),
          hint: t("collectionsHint", {
            count:
              collections?.filter(
                (item) => item.collection.current_release_number !== null
              ).length ?? 0,
          }),
        },
        {
          label: t("documents"),
          value: total((documents) => documents),
          hint: t("documentsHint"),
        },
        {
          label: t("points"),
          value: total((_documents, points) => points),
          hint: t("pointsHint"),
        },
        {
          label: t("failedJobs"),
          value:
            jobs === undefined
              ? null
              : numbers.format(
                  jobs.filter((job) => job.status === "failed").length
                ),
          hint: t("failedJobsHint", { count: RECENT_JOBS }),
        },
      ]}
    />
  )
}
