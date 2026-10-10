import { useTranslation } from "react-i18next"

import type { Quota } from "./QuotaDialog"

/** "Default" when no own quota is set, otherwise the numbers. */
export function QuotaValue({ quota }: { quota: Quota }) {
  const { t, i18n } = useTranslation("admin")
  const numbers = new Intl.NumberFormat(i18n.language)
  if (quota.text_quota_bytes === null && quota.collection_quota === null) {
    return <span className="text-muted-foreground">{t("quota.default")}</span>
  }
  return (
    <span>
      {t("quota.value", {
        text:
          quota.text_quota_bytes === null
            ? t("quota.default")
            : numbers.format(quota.text_quota_bytes),
        collections: quota.collection_quota ?? t("quota.default"),
      })}
    </span>
  )
}
