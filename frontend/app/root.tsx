import { QueryClientProvider } from "@tanstack/react-query"
import { type ReactNode, useEffect } from "react"
import { useTranslation } from "react-i18next"
import {
  isRouteErrorResponse,
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  useRouteLoaderData,
} from "react-router"
import { PreventFlashOnWrongTheme, ThemeProvider } from "remix-themes"

import { queryClient } from "~/api/query-client"
import { Document } from "~/components/document"
import { Toaster } from "~/components/ui/toast"
import { TooltipProvider } from "~/components/ui/tooltip"
import { getLocale, i18nextMiddleware } from "~/i18n/middleware.server"
import { themeSessionResolver } from "~/lib/theme.server"

import type { Route } from "./+types/root"
import stylesheet from "./app.css?url"

const HTTP_NOT_FOUND = 404

/** The global stylesheet and the favicon, linked from every page. */
export const links: Route.LinksFunction = () => [
  { rel: "stylesheet", href: stylesheet },
  { rel: "icon", href: "/favicon.svg", type: "image/svg+xml" },
]

/** Detects the request's locale and gives every loader an i18n instance for it. */
export const middleware = [i18nextMiddleware]

/**
 * The request's locale and the theme stored in the theme cookie, read by `Layout` and
 * `App`.
 */
export async function loader({ request, context }: Route.LoaderArgs) {
  const { getTheme } = await themeSessionResolver(request)
  return { locale: getLocale(context), theme: getTheme() }
}

/**
 * The HTML document around every page, error pages included: head tags, theme provider and
 * scripts. Loader data may be missing when the root loader failed.
 */
export function Layout({ children }: { children: ReactNode }) {
  const data = useRouteLoaderData<typeof loader>("root")
  const theme = data?.theme ?? null

  return (
    <ThemeProvider
      specifiedTheme={theme}
      themeAction="/actions/theme"
      disableTransitionOnThemeChange
    >
      <Document>
        <head>
          <meta charSet="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <Meta />
          <PreventFlashOnWrongTheme ssrTheme={theme !== null} />
          <Links />
        </head>
        <body>
          {children}
          <ScrollRestoration />
          <Scripts />
        </body>
      </Document>
    </ThemeProvider>
  )
}

/**
 * Provides the query client, toasts and tooltips to every route and keeps the client
 * language in step with the locale the server detected.
 */
export default function App({ loaderData }: Route.ComponentProps) {
  const { i18n } = useTranslation()

  useEffect(() => {
    if (i18n.language !== loaderData.locale) {
      void i18n.changeLanguage(loaderData.locale)
    }
  }, [i18n, loaderData.locale])

  return (
    <QueryClientProvider client={queryClient}>
      <Toaster>
        <TooltipProvider>
          <Outlet />
        </TooltipProvider>
      </Toaster>
    </QueryClientProvider>
  )
}

/**
 * The page shown when a route throws: a not-found message for 404 responses, a generic one
 * otherwise, with the stack trace in development.
 */
export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  const { t } = useTranslation("common")
  const notFound =
    isRouteErrorResponse(error) && error.status === HTTP_NOT_FOUND

  return (
    <main className="mx-auto flex min-h-svh max-w-md flex-col justify-center gap-2 p-6">
      <h1 className="text-2xl font-semibold">
        {notFound ? t("errorPage.notFoundTitle") : t("errorPage.title")}
      </h1>
      <p className="text-muted-foreground">
        {notFound
          ? t("errorPage.notFoundDescription")
          : t("errorPage.description")}
      </p>
      {import.meta.env.DEV && error instanceof Error ? (
        <pre className="overflow-x-auto text-xs">{error.stack}</pre>
      ) : null}
    </main>
  )
}
