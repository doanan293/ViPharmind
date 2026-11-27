import { useTranslation } from "react-i18next"
import { redirect } from "react-router"

import { getUsersCurrentUserQueryKey } from "~/api/gen/endpoints"
import { isApiError, UNKNOWN_ERROR_CODE } from "~/api/problem"
import { queryClient } from "~/api/query-client"
import { Spinner } from "~/components/ui/spinner"
import { completeGoogleLink } from "~/features/settings/lib/google-link"

import type { Route } from "./+types/google-link-callback"

/**
 * Links a Google account to the signed-in user and returns to the settings page, with the
 * error code when linking failed. It always throws a redirect.
 */
export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  try {
    await completeGoogleLink(new URL(request.url))
  } catch (error) {
    const code = isApiError(error) ? error.code : UNKNOWN_ERROR_CODE
    throw redirect(`/settings?error=${encodeURIComponent(code)}`)
  }
  await queryClient.invalidateQueries({
    queryKey: getUsersCurrentUserQueryKey(),
  })
  throw redirect("/settings")
}

/** The progress message shown while the Google account is linked. */
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
export default function GoogleLinkCallback() {
  return <HydrateFallback />
}
