import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"
import { z } from "zod"

import {
  getUsersCurrentUserQueryKey,
  useAuthCookieLogin,
  useAuthEmailVerifyRequest,
} from "~/api/gen/endpoints"
import { AuthCookieLoginBody } from "~/api/gen/zod"
import { isApiError } from "~/api/problem"
import {
  requestVerificationCode,
  type VerificationRequest,
} from "~/features/auth/components/VerifyEmailStep"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"

const loginSchema = AuthCookieLoginBody.pick({
  username: true,
  password: true,
}).extend({
  username: z.email(),
  password: z.string().min(1),
})

/** The email and password the sign-in form submits. */
export type LoginValues = z.infer<typeof loginSchema>

const LOGIN_FIELDS = ["username", "password"] as const

/**
 * Form state and submit handler for email sign-in. A correct login goes to `nextPath`; an
 * unverified email sends a code and returns it as `unverified` for the verify step.
 */
export function useLoginForm(nextPath: string) {
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const login = useAuthCookieLogin({
    mutation: { meta: { skipAuthRedirect: true } },
  })
  const requestCode = useAuthEmailVerifyRequest({
    mutation: { meta: { skipAuthRedirect: true } },
  })
  const [unverified, setUnverified] = useState<VerificationRequest | null>(null)
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: "", password: "" },
  })

  async function onSubmit(values: LoginValues) {
    try {
      await login.mutateAsync({ data: values })
    } catch (error) {
      if (isApiError(error) && error.code === "EMAIL_NOT_VERIFIED") {
        setUnverified(
          await requestVerificationCode(
            (email) => requestCode.mutateAsync({ data: { email } }),
            values.username,
            values.password
          )
        )
        return
      }
      applyApiError(
        error,
        form.setError,
        LOGIN_FIELDS,
        apiErrorMessage(error, tErrors)
      )
      return
    }
    await queryClient.invalidateQueries({
      queryKey: getUsersCurrentUserQueryKey(),
    })
    await navigate(nextPath, { replace: true })
  }

  return { form, onSubmit, unverified }
}
