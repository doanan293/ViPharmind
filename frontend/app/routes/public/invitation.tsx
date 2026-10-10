import { useTranslation } from "react-i18next"
import { useParams } from "react-router"

import { useLogout } from "~/features/auth/hooks/use-logout"
import { InvitationLanding } from "~/features/organizations/components/InvitationLanding"

export default function InvitationRoute() {
  const { t } = useTranslation("organizations")
  const { token = "" } = useParams()
  const logout = useLogout()
  return (
    <main className="flex min-h-svh items-center justify-center p-4">
      <title>{t("landing.title")}</title>
      <InvitationLanding token={token} onSignOut={logout} />
    </main>
  )
}
