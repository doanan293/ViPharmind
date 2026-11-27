import type { ParseKeys } from "i18next"
import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"

/** A translation key of the admin namespace. */
export type AdminKey = ParseKeys<"admin">

/** A column header translated in the admin namespace. */
export function AdminHeader({ k }: { k: AdminKey }): ReactNode {
  const { t } = useTranslation("admin")
  return t(k)
}

/** Dates as the admin tables show them. */
export function DateCell({
  value,
  time = false,
}: {
  value: string | null
  time?: boolean
}): ReactNode {
  const { i18n } = useTranslation()
  if (value === null || value === "") return ""
  return new Intl.DateTimeFormat(i18n.language, {
    dateStyle: time ? "short" : "medium",
    ...(time ? { timeStyle: "short" as const } : {}),
  }).format(new Date(value))
}

/** A number formatted for the interface language. */
export function NumberCell({ value }: { value: number }): ReactNode {
  const { i18n } = useTranslation()
  return new Intl.NumberFormat(i18n.language).format(value)
}

/** Labels for the column picker, from the same keys as the headers. */
export function useColumnLabels(keys: Readonly<Record<string, AdminKey>>) {
  const { t } = useTranslation("admin")
  return Object.fromEntries(
    Object.entries(keys).map(([id, key]) => [id, t(key)])
  )
}
