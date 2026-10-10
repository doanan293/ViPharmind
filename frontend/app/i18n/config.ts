import type { InitOptions, Resource } from "i18next"

import enAuth from "./resources/en/auth.json"
import enChat from "./resources/en/chat.json"
import enCitations from "./resources/en/citations.json"
import enCommon from "./resources/en/common.json"
import enErrors from "./resources/en/errors.json"
import enLanding from "./resources/en/landing.json"
import enAudit from "./resources/en/audit.json"
import enOrganizations from "./resources/en/organizations.json"
import enCollections from "./resources/en/collections.json"
import enAdmin from "./resources/en/admin.json"
import enSettings from "./resources/en/settings.json"
import viAuth from "./resources/vi/auth.json"
import viChat from "./resources/vi/chat.json"
import viCitations from "./resources/vi/citations.json"
import viCommon from "./resources/vi/common.json"
import viErrors from "./resources/vi/errors.json"
import viLanding from "./resources/vi/landing.json"
import viAudit from "./resources/vi/audit.json"
import viOrganizations from "./resources/vi/organizations.json"
import viCollections from "./resources/vi/collections.json"
import viAdmin from "./resources/vi/admin.json"
import viSettings from "./resources/vi/settings.json"

export const SUPPORTED_LANGUAGES = ["vi", "en"] as const
export type Language = (typeof SUPPORTED_LANGUAGES)[number]
export const FALLBACK_LANGUAGE: Language = "vi"

export const NAMESPACES = [
  "common",
  "auth",
  "chat",
  "citations",
  "settings",
  "landing",
  "errors",
  "audit",
  "organizations",
  "collections",
  "admin",
] as const
export type Namespace = (typeof NAMESPACES)[number]

export const resources = {
  vi: {
    common: viCommon,
    auth: viAuth,
    chat: viChat,
    citations: viCitations,
    settings: viSettings,
    landing: viLanding,
    errors: viErrors,
    admin: viAdmin,
    collections: viCollections,
    organizations: viOrganizations,
    audit: viAudit,
  },
  en: {
    common: enCommon,
    auth: enAuth,
    chat: enChat,
    citations: enCitations,
    settings: enSettings,
    landing: enLanding,
    errors: enErrors,
    admin: enAdmin,
    collections: enCollections,
    organizations: enOrganizations,
    audit: enAudit,
  },
} satisfies Resource

export const i18nextOptions = {
  fallbackLng: FALLBACK_LANGUAGE,
  supportedLngs: SUPPORTED_LANGUAGES,
  ns: [...NAMESPACES],
  defaultNS: "common",
  resources,
  interpolation: { escapeValue: false },
} satisfies InitOptions

export function isLanguage(value: unknown): value is Language {
  return SUPPORTED_LANGUAGES.some((language) => language === value)
}

/** Only public pages carry a language prefix, and only for non-default languages. */
export function localeFromPath(pathname: string): Language | null {
  const firstSegment = pathname.split("/")[1]
  return (
    SUPPORTED_LANGUAGES.find(
      (language) => language !== FALLBACK_LANGUAGE && language === firstSegment
    ) ?? null
  )
}

/** Public pages besides the landing page; each also exists under `/en`. */
export const PUBLIC_PAGE_PATHS = ["/privacy", "/terms"] as const

/** Public pages get their language from the URL so SSR, prerendered files and hreflang agree. */
export function publicPageLocale(pathname: string): Language | null {
  if (pathname === "/" || PUBLIC_PAGE_PATHS.some((path) => path === pathname)) {
    return FALLBACK_LANGUAGE
  }
  return localeFromPath(pathname)
}

/**
 * The page path behind a React Router single-fetch data request.
 *
 * Middleware sees the raw request URL (`/_.data`, `/en.data`, `/en/_.data`); React Router
 * normalizes it internally with the same two rules but does not export that helper.
 */
export function documentPathname(pathname: string): string {
  if (pathname.endsWith("/_.data")) {
    return pathname.slice(0, -"_.data".length)
  }
  return pathname.endsWith(".data")
    ? pathname.slice(0, -".data".length)
    : pathname
}
