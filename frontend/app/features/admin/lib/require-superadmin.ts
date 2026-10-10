import { data, type LoaderFunctionArgs } from "react-router"

import type { AccountView } from "~/api/gen/schemas"
import { requireUser } from "~/features/auth/lib/require-user"

/** The console does not exist for anyone else: a 404, not a 403, so it is not advertised. */
export async function requireSuperadmin(
  request: Request
): Promise<AccountView> {
  const user = await requireUser(request)
  if (!user.is_superadmin) {
    throw data(null, { status: 404 })
  }
  return user
}

export async function adminLoader({ request }: LoaderFunctionArgs) {
  return { user: await requireSuperadmin(request) }
}
