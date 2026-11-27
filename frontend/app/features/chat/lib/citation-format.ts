import { useCallback } from "react"
import { useTranslation } from "react-i18next"

/** The i18n key and values for a page reference, or null when the source has no pages. */
export type PageLabel =
  | { key: "pages.single"; page: number }
  | { key: "pages.range"; start: number; end: number }
  | null

/** Describes a page reference as one page or a range; a missing end falls back to the other end. */
export function pageLabel(
  startPage: number | null,
  endPage: number | null
): PageLabel {
  if (startPage === null && endPage === null) {
    return null
  }
  if (startPage === null || endPage === null || startPage === endPage) {
    return { key: "pages.single", page: startPage ?? endPage ?? 0 }
  }
  return { key: "pages.range", start: startPage, end: endPage }
}

/** Returns a stable function that formats a page reference in the current language, or null without pages. */
export function usePageText(): (
  startPage: number | null,
  endPage: number | null
) => string | null {
  const { t } = useTranslation("citations")
  return useCallback(
    (startPage: number | null, endPage: number | null) => {
      const label = pageLabel(startPage, endPage)
      if (label === null) {
        return null
      }
      return label.key === "pages.single"
        ? t("pages.single", { page: label.page })
        : t("pages.range", { start: label.start, end: label.end })
    },
    [t]
  )
}
