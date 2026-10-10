import { useTranslation } from "react-i18next"

import { useAuditMineInfinite } from "~/api/gen/endpoints"

import { AuditList } from "./AuditList"

const PAGE_SIZE = 50

export function MyActivity() {
  const { t } = useTranslation("audit")
  const query = useAuditMineInfinite(
    { limit: PAGE_SIZE },
    {
      query: {
        initialPageParam: undefined,
        getNextPageParam: (page) => page.next_cursor ?? undefined,
      },
    }
  )
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-4 md:p-8">
      <title>{t("page.title")}</title>
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">{t("page.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("page.description")}</p>
      </div>
      <AuditList query={query} />
    </div>
  )
}
