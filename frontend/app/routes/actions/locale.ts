import { setLocale } from "~/i18n/locale.server"

import type { Route } from "./+types/locale"

/** Stores the language the user picked in the locale cookie. */
export function action({ request }: Route.ActionArgs) {
  return setLocale(request)
}
