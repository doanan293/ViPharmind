import { useTranslation } from "react-i18next"
import { data, Link } from "react-router"

import { buttonVariants } from "~/components/ui/button"

/** Answers unknown paths with HTTP 404 so crawlers do not index them. */
export function loader() {
  return data(null, { status: 404 })
}

/** The translated not-found page with a link to the home page. */
export default function NotFound() {
  const { t } = useTranslation("common")

  return (
    <main className="mx-auto flex min-h-svh max-w-md flex-col items-start justify-center gap-3 p-6">
      <h1 className="text-2xl font-semibold">{t("errorPage.notFoundTitle")}</h1>
      <p className="text-muted-foreground">
        {t("errorPage.notFoundDescription")}
      </p>
      <Link to="/" className={buttonVariants({ variant: "outline" })}>
        {t("errorPage.backHome")}
      </Link>
    </main>
  )
}
