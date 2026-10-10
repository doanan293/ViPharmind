import { Link } from "react-router"

import type { Language } from "~/i18n/config"

import { LEGAL_LINK_LABELS, LEGAL_PATHS } from "../lib/content"

/** Links to the privacy policy and terms in the page's language. */
export function SiteFooter({ locale }: { locale: Language }) {
  return (
    <footer className="border-t">
      <nav className="mx-auto flex max-w-5xl flex-wrap gap-4 px-4 py-6 text-sm text-muted-foreground md:px-8">
        <span>© 2026 ViPharMind</span>
        <Link
          to={LEGAL_PATHS.privacy[locale]}
          className="underline-offset-4 hover:underline"
        >
          {LEGAL_LINK_LABELS.privacy[locale]}
        </Link>
        <Link
          to={LEGAL_PATHS.terms[locale]}
          className="underline-offset-4 hover:underline"
        >
          {LEGAL_LINK_LABELS.terms[locale]}
        </Link>
      </nav>
    </footer>
  )
}
