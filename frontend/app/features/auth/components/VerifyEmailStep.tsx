import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

import {
  getUsersCurrentUserQueryKey,
  useAuthEmailVerify,
  useAuthEmailVerifyRequest,
} from "~/api/gen/endpoints"
import { CodeStep } from "~/components/code-step"

const SKIP_AUTH_REDIRECT = { mutation: { meta: { skipAuthRedirect: true } } }

export type VerificationRequest = {
  email: string
  /** Needed with the code: the server signs in only whoever knows it. */
  password: string
  /** Why the code was not sent, or null when it was. */
  sendError: unknown
}

/** Ask for a verification code and keep the outcome for VerifyEmailStep. */
export async function requestVerificationCode(
  send: (email: string) => Promise<unknown>,
  email: string,
  password: string
): Promise<VerificationRequest> {
  try {
    await send(email)
    return { email, password, sendError: null }
  } catch (error: unknown) {
    return { email, password, sendError: error }
  }
}

/** Verifies the email with the code just sent; a correct code also signs the user in. */
export function VerifyEmailStep({
  request,
  nextPath,
}: {
  request: VerificationRequest
  nextPath: string
}) {
  const { email, password, sendError } = request
  const { t } = useTranslation("auth")
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const verify = useAuthEmailVerify(SKIP_AUTH_REDIRECT)
  const resend = useAuthEmailVerifyRequest(SKIP_AUTH_REDIRECT)

  return (
    <CodeStep
      id="verify-email-code"
      description={t("verifyEmail.sentTo", { email })}
      submitLabel={t("verifyEmail.submit")}
      sendError={sendError}
      onSubmit={async (code) => {
        await verify.mutateAsync({ data: { email, code, password } })
        await queryClient.invalidateQueries({
          queryKey: getUsersCurrentUserQueryKey(),
        })
        await navigate(nextPath, { replace: true })
      }}
      onResend={async () => {
        await resend.mutateAsync({ data: { email } })
      }}
    />
  )
}
