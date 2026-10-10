import type { AccountView } from "~/api/gen/schemas"

/** How the shell names the signed-in account: phone-only accounts have no email. */
export function accountLabel(user: AccountView): string {
  if (user.display_name !== "") {
    return user.display_name
  }
  return user.email ?? user.phone_number ?? ""
}
