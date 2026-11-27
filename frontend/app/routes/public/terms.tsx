import { LegalPage } from "~/features/legal/components/LegalPage"
import { legalMeta } from "~/features/legal/lib/meta"
import { FALLBACK_LANGUAGE, isLanguage } from "~/i18n/config"
import { getLocale } from "~/i18n/middleware.server"

import type { Route } from "./+types/terms"

const DEFAULT_SITE_URL = "http://localhost:8080"

/** The page's locale and the public site URL for the canonical and hreflang links. */
export function loader({ context }: Route.LoaderArgs) {
  const detected = getLocale(context)
  return {
    locale: isLanguage(detected) ? detected : FALLBACK_LANGUAGE,
    siteUrl: process.env.PUBLIC_SITE_URL ?? DEFAULT_SITE_URL,
  }
}

/** Description, canonical and hreflang links of the terms of use. */
export const meta: Route.MetaFunction = ({ loaderData }) =>
  loaderData === undefined
    ? []
    : legalMeta("terms", loaderData.locale, loaderData.siteUrl)

/** The terms of use at `/terms` (Vietnamese) and `/en/terms` (English). */
export default function TermsRoute({ loaderData }: Route.ComponentProps) {
  return <LegalPage document="terms" locale={loaderData.locale} />
}
