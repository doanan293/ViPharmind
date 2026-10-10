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

/** Verifies the email with the code just sent; a correct code also signs the user in. */
export function VerifyEmailStep({
  email,
  nextPath,
}: {
  email: string
  nextPath: string
}) {
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
      onSubmit={async (code) => {
        await verify.mutateAsync({ data: { email, code } })
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
