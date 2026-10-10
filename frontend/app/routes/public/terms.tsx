import { LegalPage } from "~/features/legal/components/LegalPage"
import { legalMeta } from "~/features/legal/lib/meta"
import { FALLBACK_LANGUAGE, isLanguage } from "~/i18n/config"
import { getLocale } from "~/i18n/middleware.server"

import type { Route } from "./+types/terms"

const DEFAULT_SITE_URL = "http://localhost:8080"

export function loader({ context }: Route.LoaderArgs) {
  const detected = getLocale(context)
  return {
    locale: isLanguage(detected) ? detected : FALLBACK_LANGUAGE,
    siteUrl: process.env.PUBLIC_SITE_URL ?? DEFAULT_SITE_URL,
  }
}

export const meta: Route.MetaFunction = ({ loaderData }) =>
  loaderData === undefined
    ? []
    : legalMeta("terms", loaderData.locale, loaderData.siteUrl)

export default function TermsRoute({ loaderData }: Route.ComponentProps) {
  return <LegalPage document="terms" locale={loaderData.locale} />
}
