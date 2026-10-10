import { useTranslation } from "react-i18next"
import { Link } from "react-router"

import { FALLBACK_LANGUAGE, type Language, isLanguage } from "~/i18n/config"

import { LEGAL_LINK_LABELS, LEGAL_PATHS } from "../lib/content"

const CONSENT: Record<Language, [string, string, string]> = {
  vi: ["Khi tạo tài khoản, bạn đồng ý với ", " và ", "."],
  en: ["By creating an account you agree to the ", " and the ", "."],
}

function useLanguage(): Language {
  const { i18n } = useTranslation()
  return isLanguage(i18n.language) ? i18n.language : FALLBACK_LANGUAGE
}

function LegalLink({
  document,
  locale,
}: {
  document: "privacy" | "terms"
  locale: Language
}) {
  return (
    <Link
      to={LEGAL_PATHS[document][locale]}
      className="underline underline-offset-4"
    >
      {LEGAL_LINK_LABELS[document][locale]}
    </Link>
  )
}

/** The consent line under the registration form. */
export function LegalConsent() {
  const locale = useLanguage()
  const [before, middle, after] = CONSENT[locale]
  return (
    <p className="text-center text-xs text-muted-foreground">
      {before}
      <LegalLink document="terms" locale={locale} />
      {middle}
      <LegalLink document="privacy" locale={locale} />
      {after}
    </p>
  )
}

/** Both legal pages as a row of links, in the UI language. */
export function LegalLinks() {
  const locale = useLanguage()
  return (
    <nav className="flex gap-4 text-sm text-muted-foreground">
      <LegalLink document="privacy" locale={locale} />
      <LegalLink document="terms" locale={locale} />
    </nav>
  )
}
