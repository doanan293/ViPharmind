import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Link, useNavigate } from "react-router"

import {
  useInvitationsAccept,
  useInvitationsDecline,
  useInvitationsPreview,
  useUsersCurrentUser,
} from "~/api/gen/endpoints"
import { isApiError } from "~/api/problem"
import { Button, buttonVariants } from "~/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import { Spinner } from "~/components/ui/spinner"
import { apiErrorMessage } from "~/i18n/error-message"

const SKIP_AUTH = { meta: { skipAuthRedirect: true }, retry: false } as const

/** Public page of an invitation link: preview, then join or decline once signed in. */
export function InvitationLanding({
  token,
  onSignOut,
}: {
  token: string
  onSignOut: () => Promise<void>
}) {
  const { t } = useTranslation("organizations")
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const preview = useInvitationsPreview(token, { query: SKIP_AUTH })
  const user = useUsersCurrentUser({ query: SKIP_AUTH })
  const accept = useInvitationsAccept({
    mutation: { meta: { skipAuthRedirect: true } },
  })
  const decline = useInvitationsDecline({
    mutation: { meta: { skipAuthRedirect: true } },
  })
  const [problem, setProblem] = useState<string | null>(null)
  const [declined, setDeclined] = useState(false)
  const next = encodeURIComponent(`/invitations/${token}`)

  if (preview.isPending || user.isPending) {
    return <Spinner />
  }
  if (preview.data === undefined) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t("landing.invalid")}
      </p>
    )
  }
  const invitation = preview.data
  const wrongEmail = problem === "INVITATION_EMAIL_MISMATCH"

  function fail(error: unknown) {
    // A mismatched email gets its own message and a sign-out button.
    setProblem(
      isApiError(error) && error.code === "INVITATION_EMAIL_MISMATCH"
        ? error.code
        : apiErrorMessage(error, tErrors)
    )
  }

  return (
    <Card className="mx-auto w-full max-w-md">
      <CardHeader>
        <CardTitle>{t("landing.title")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p>
          {t("landing.body", {
            inviter: invitation.inviter_name,
            organization: invitation.organization_name,
            role: t(`role.${invitation.role}`),
          })}
        </p>
        <p className="text-sm text-muted-foreground">
          {t("landing.forEmail", { email: invitation.email_hint })}
        </p>
        {declined ? (
          <p className="text-sm">{t("landing.declined")}</p>
        ) : user.data === undefined ? (
          <div className="flex flex-wrap gap-2">
            <Link to={`/login?next=${next}`} className={buttonVariants()}>
              {t("landing.signIn")}
            </Link>
            <Link
              to={`/register?next=${next}`}
              className={buttonVariants({ variant: "outline" })}
            >
              {t("landing.register")}
            </Link>
          </div>
        ) : wrongEmail ? (
          <div className="flex flex-col gap-3">
            <p role="alert" className="text-sm text-destructive">
              {t("landing.wrongEmail", { email: invitation.email_hint })}
            </p>
            <Button
              variant="outline"
              className="self-start"
              onClick={() => void onSignOut()}
            >
              {t("landing.signOut")}
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {problem === null ? null : (
              <p role="alert" className="text-sm text-destructive">
                {problem}
              </p>
            )}
            <div className="flex gap-2">
              <Button
                disabled={accept.isPending}
                onClick={() =>
                  accept.mutate(
                    { token },
                    {
                      onSuccess: (organization) =>
                        void navigate(`/organizations/${organization.id}`),
                      onError: fail,
                    }
                  )
                }
              >
                {t("landing.accept")}
              </Button>
              <Button
                variant="outline"
                disabled={decline.isPending}
                onClick={() =>
                  decline.mutate(
                    { token },
                    { onSuccess: () => setDeclined(true), onError: fail }
                  )
                }
              >
                {t("landing.decline")}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
