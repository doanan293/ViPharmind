import { LandingPage } from "~/features/landing/components/LandingPage"
import { landingMeta } from "~/features/landing/lib/meta"
import { SiteFooter } from "~/features/legal/components/SiteFooter"
import { FALLBACK_LANGUAGE, isLanguage } from "~/i18n/config"
import { getInstance, getLocale } from "~/i18n/middleware.server"

import type { Route } from "./+types/landing"

const DEFAULT_SITE_URL = "http://localhost:8080"

/**
 * The landing page's locale, translated title and description, and the public site URL for
 * absolute links in the meta tags.
 */
export function loader({ context }: Route.LoaderArgs) {
  const detected = getLocale(context)
  const locale = isLanguage(detected) ? detected : FALLBACK_LANGUAGE
  const t = getInstance(context).getFixedT(locale, "landing")

  return {
    locale,
    title: t("meta.title"),
    description: t("meta.description"),
    siteUrl: process.env.PUBLIC_SITE_URL ?? DEFAULT_SITE_URL,
  }
}

/** Title, description, Open Graph and hreflang tags of the landing page. */
export const meta: Route.MetaFunction = ({ loaderData }) =>
  loaderData === undefined ? [] : landingMeta(loaderData)

/** The public landing page at `/` (Vietnamese) and `/en/` (English). */
export default function Landing({ loaderData }: Route.ComponentProps) {
  return (
    <>
      <LandingPage locale={loaderData.locale} />
      <SiteFooter locale={loaderData.locale} />
    </>
  )
}
