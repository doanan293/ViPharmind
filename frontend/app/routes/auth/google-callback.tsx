import { useTranslation } from "react-i18next"
import { redirect } from "react-router"

import { getUsersCurrentUserQueryKey } from "~/api/gen/endpoints"
import { isApiError, UNKNOWN_ERROR_CODE } from "~/api/problem"
import { queryClient } from "~/api/query-client"
import { Spinner } from "~/components/ui/spinner"
import { completeGoogleLogin } from "~/features/auth/lib/google"

import type { Route } from "./+types/google-callback"

/**
 * Finishes a Google sign-in and redirects to the page the user started from, or back to
 * the login page with the error code. It always throws a redirect.
 */
export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  let nextPath: string
  try {
    nextPath = await completeGoogleLogin(new URL(request.url))
  } catch (error) {
    const code = isApiError(error) ? error.code : UNKNOWN_ERROR_CODE
    throw redirect(`/login?error=${encodeURIComponent(code)}`)
  }
  await queryClient.invalidateQueries({
    queryKey: getUsersCurrentUserQueryKey(),
  })
  throw redirect(nextPath)
}

/** The progress message shown while the Google sign-in completes. */
export function HydrateFallback() {
  const { t } = useTranslation("auth")
  return (
    <main className="flex min-h-svh items-center justify-center gap-2 text-sm text-muted-foreground">
      <Spinner />
      <span>{t("googleCompleting")}</span>
    </main>
  )
}

/** Shows the progress message; the client loader redirects before anything else renders. */
export default function GoogleCallback() {
  return <HydrateFallback />
}
