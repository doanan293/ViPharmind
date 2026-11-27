import {
  ActivityIcon,
  LibraryIcon,
  QuoteIcon,
  ShieldCheckIcon,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router"
import { BrandMark } from "~/components/brand-mark"

import { buttonVariants } from "~/components/ui/button"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { LANDING_PATHS } from "~/features/landing/lib/meta"
import type { Language } from "~/i18n/config"

const FEATURES = [
  { key: "citations", Icon: QuoteIcon },
  { key: "streaming", Icon: ActivityIcon },
  { key: "collections", Icon: LibraryIcon },
  { key: "guard", Icon: ShieldCheckIcon },
] as const

/**
 * The public landing page in `locale`: hero with sign-in and register links, feature cards
 * and a link to the other language.
 */
export function LandingPage({ locale }: { locale: Language }) {
  const { t } = useTranslation("landing")
  const otherLocale: Language = locale === "vi" ? "en" : "vi"

  return (
    <div className="min-h-svh bg-background text-foreground">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
        <BrandMark />
        <Link
          to={LANDING_PATHS[otherLocale]}
          hrefLang={otherLocale}
          lang={otherLocale}
          className={buttonVariants({ variant: "ghost", size: "sm" })}
        >
          {t("language.switch")}
        </Link>
      </header>

      <main className="mx-auto flex max-w-5xl flex-col gap-16 px-6 pt-12 pb-16">
        <section className="flex flex-col items-start gap-4">
          <h1 className="text-4xl font-semibold tracking-tight text-balance">
            {t("hero.title")}
          </h1>
          <p className="max-w-2xl text-lg text-muted-foreground">
            {t("hero.subtitle")}
          </p>
          <div className="flex flex-wrap gap-3">
            <Link to="/login" className={buttonVariants({ size: "lg" })}>
              {t("hero.signIn")}
            </Link>
            <Link
              to="/register"
              className={buttonVariants({ variant: "outline", size: "lg" })}
            >
              {t("hero.register")}
            </Link>
          </div>
        </section>

        <section
          aria-labelledby="features-title"
          className="flex flex-col gap-6"
        >
          <h2 id="features-title" className="text-2xl font-semibold">
            {t("features.title")}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {FEATURES.map(({ key, Icon }) => (
              <Card key={key}>
                <CardHeader>
                  <Icon
                    aria-hidden="true"
                    className="mb-2 size-5 text-primary"
                  />
                  <CardTitle>{t(`features.${key}.title`)}</CardTitle>
                  <CardDescription>
                    {t(`features.${key}.description`)}
                  </CardDescription>
                </CardHeader>
              </Card>
            ))}
          </div>
        </section>

        <section
          aria-labelledby="sources-title"
          className="flex flex-col gap-4"
        >
          <h2 id="sources-title" className="text-2xl font-semibold">
            {t("sources.title")}
          </h2>
          <ul className="list-disc pl-6 text-muted-foreground">
            <li>{t("sources.formulary")}</li>
            <li>{t("sources.leaflets")}</li>
          </ul>
        </section>
      </main>
    </div>
  )
}
