import { redirect } from "react-router"

import type { AccountView } from "~/api/gen/schemas"
import { HttpStatus } from "~/api/http-status"
import { isApiError } from "~/api/problem"
import { queryClient } from "~/api/query-client"
import { currentUserQueryOptions } from "~/features/auth/lib/current-user"

/**
 * Route loader guard: resolves the signed-in account, or throws a redirect to /login that
 * comes back to the requested path once the user signs in.
 */
export async function requireUser(request: Request): Promise<AccountView> {
  try {
    return await queryClient.ensureQueryData(currentUserQueryOptions())
  } catch (error) {
    if (isApiError(error) && error.status === HttpStatus.UNAUTHORIZED) {
      const url = new URL(request.url)
      throw redirect(
        `/login?next=${encodeURIComponent(url.pathname + url.search)}`
      )
    }
    throw error
  }
}
