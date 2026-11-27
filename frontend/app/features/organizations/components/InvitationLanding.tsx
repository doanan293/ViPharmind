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
import { Alert, AlertDescription } from "~/components/ui/alert"
import { Button, buttonVariants } from "~/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import { Spinner } from "~/components/ui/spinner"
import { apiErrorMessage } from "~/i18n/error-message"

const SKIP_AUTH = { meta: { skipAuthRedirect: true }, retry: false } as const

const EMAIL_MISMATCH = "INVITATION_EMAIL_MISMATCH"

/** Sign-in and register links that come back to this invitation afterwards. */
function SignInLinks({ token }: { token: string }) {
  const { t } = useTranslation("organizations")
  const next = encodeURIComponent(`/invitations/${token}`)
  return (
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
  )
}

/** The signed-in account is not the invited one: say so and offer to sign out. */
function WrongEmail({
  emailHint,
  onSignOut,
}: {
  emailHint: string
  onSignOut: () => Promise<void>
}) {
  const { t } = useTranslation("organizations")
  return (
    <div className="flex flex-col gap-3">
      <Alert variant="destructive">
        <AlertDescription>
          {t("landing.wrongEmail", { email: emailHint })}
        </AlertDescription>
      </Alert>
      <Button
        variant="outline"
        className="self-start"
        onClick={() => void onSignOut()}
      >
        {t("landing.signOut")}
      </Button>
    </div>
  )
}

/** Accept (opens the organization) or decline the invitation as the signed-in user. */
function InvitationResponse({
  token,
  emailHint,
  onSignOut,
  onDeclined,
}: {
  token: string
  emailHint: string
  onSignOut: () => Promise<void>
  onDeclined: () => void
}) {
  const { t } = useTranslation("organizations")
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const accept = useInvitationsAccept({
    mutation: { meta: { skipAuthRedirect: true } },
  })
  const decline = useInvitationsDecline({
    mutation: { meta: { skipAuthRedirect: true } },
  })
  const [problem, setProblem] = useState<string | null>(null)

  function fail(error: unknown) {
    // A mismatched email gets its own message and a sign-out button.
    setProblem(
      isApiError(error) && error.code === EMAIL_MISMATCH
        ? error.code
        : apiErrorMessage(error, tErrors)
    )
  }

  if (problem === EMAIL_MISMATCH) {
    return <WrongEmail emailHint={emailHint} onSignOut={onSignOut} />
  }
  return (
    <div className="flex flex-col gap-3">
      {problem === null ? null : (
        <Alert variant="destructive">
          <AlertDescription>{problem}</AlertDescription>
        </Alert>
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
            decline.mutate({ token }, { onSuccess: onDeclined, onError: fail })
          }
        >
          {t("landing.decline")}
        </Button>
      </div>
    </div>
  )
}

/** Public page of an invitation link: preview, then join or decline once signed in. */
export function InvitationLanding({
  token,
  onSignOut,
}: {
  token: string
  onSignOut: () => Promise<void>
}) {
  const { t } = useTranslation("organizations")
  const preview = useInvitationsPreview(token, { query: SKIP_AUTH })
  const user = useUsersCurrentUser({ query: SKIP_AUTH })
  const [declined, setDeclined] = useState(false)

  if (preview.status === "pending" || user.status === "pending") {
    return <Spinner />
  }
  if (preview.data === undefined) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{t("landing.invalid")}</AlertDescription>
      </Alert>
    )
  }
  const invitation = preview.data

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
          <SignInLinks token={token} />
        ) : (
          <InvitationResponse
            token={token}
            emailHint={invitation.email_hint}
            onSignOut={onSignOut}
            onDeclined={() => setDeclined(true)}
          />
        )}
      </CardContent>
    </Card>
  )
}
