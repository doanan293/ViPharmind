import { Link } from "react-router"

import type { Language } from "~/i18n/config"

import { LEGAL_TEXT, type LegalDocument } from "../lib/content"
import { SiteFooter } from "./SiteFooter"

const UPDATED_LABEL: Record<Language, string> = {
  vi: "Cập nhật ngày",
  en: "Last updated",
}

const HOME_PATH: Record<Language, string> = { vi: "/", en: "/en/" }

/**
 * A legal page (privacy policy or terms) in `locale`, with its own `<title>` and the site
 * footer. Its text is not translated through i18n: each language has its own version.
 */
export function LegalPage({
  document,
  locale,
}: {
  document: LegalDocument
  locale: Language
}) {
  const text = LEGAL_TEXT[document][locale]
  const updated = new Intl.DateTimeFormat(locale, { dateStyle: "long" }).format(
    new Date(text.updated)
  )
  return (
    <div lang={locale} className="flex min-h-svh flex-col">
      <title>{`${text.title} · ViPharmind`}</title>
      <header className="mx-auto w-full max-w-3xl px-4 pt-8 md:px-8">
        <Link
          to={HOME_PATH[locale]}
          className="text-sm font-semibold underline-offset-4 hover:underline"
        >
          ViPharmind
        </Link>
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8 md:px-8">
        <article className="prose prose-neutral dark:prose-invert max-w-none">
          <h1>{text.title}</h1>
          <p className="lead">{text.description}</p>
          <p className="text-sm">
            {UPDATED_LABEL[locale]} {updated}
          </p>
          {text.sections.map((section) => (
            <section key={section.heading}>
              <h2>{section.heading}</h2>
              {section.paragraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </section>
          ))}
        </article>
      </main>
      <SiteFooter locale={locale} />
    </div>
  )
}
