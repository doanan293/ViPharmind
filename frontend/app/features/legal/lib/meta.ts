import type { MetaDescriptor } from "react-router"

import type { Language } from "~/i18n/config"

import { type LegalDocument, LEGAL_PATHS, LEGAL_TEXT } from "./content"

/** Description, canonical URL and the hreflang pair; LegalPage renders the <title>. */
export function legalMeta(
  document: LegalDocument,
  locale: Language,
  siteUrl: string
): MetaDescriptor[] {
  const text = LEGAL_TEXT[document][locale]
  const absolute = (language: Language) =>
    new URL(LEGAL_PATHS[document][language], siteUrl).toString()
  return [
    { name: "description", content: text.description },
    { tagName: "link", rel: "canonical", href: absolute(locale) },
    { tagName: "link", rel: "alternate", hrefLang: "vi", href: absolute("vi") },
    { tagName: "link", rel: "alternate", hrefLang: "en", href: absolute("en") },
    {
      tagName: "link",
      rel: "alternate",
      hrefLang: "x-default",
      href: absolute("vi"),
    },
  ]
}
