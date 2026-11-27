import { zodResolver } from "@hookform/resolvers/zod"
import { useMemo, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"

import {
  useAuthEmailVerifyRequest,
  useRegisterRegister,
} from "~/api/gen/endpoints"
import { RegisterRegisterBody } from "~/api/gen/zod"
import {
  requestVerificationCode,
  type VerificationRequest,
} from "~/features/auth/components/VerifyEmailStep"
import { passwordSchema } from "~/features/auth/lib/password"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"

/** Longest display name the server accepts. */
const DISPLAY_NAME_MAX_LENGTH = 100

/** Built per render language so the password message is translated. */
function createRegisterSchema(passwordTooShort: string) {
  return RegisterRegisterBody.pick({
    email: true,
    password: true,
    display_name: true,
  }).extend({
    password: passwordSchema(passwordTooShort),
    display_name: z.string().trim().max(DISPLAY_NAME_MAX_LENGTH),
  })
}

/** The fields the registration form submits. */
export type RegisterValues = z.infer<ReturnType<typeof createRegisterSchema>>

const REGISTER_FIELDS = ["email", "password", "display_name"] as const

/**
 * Form state and submit handler for email registration. Once the account exists, `registered`
 * holds the verification request the email code step needs.
 */
export function useRegisterForm() {
  const { t } = useTranslation("auth")
  const { t: tErrors } = useTranslation("errors")
  const register = useRegisterRegister({
    mutation: { meta: { skipAuthRedirect: true } },
  })
  const requestCode = useAuthEmailVerifyRequest({
    mutation: { meta: { skipAuthRedirect: true } },
  })
  const [registered, setRegistered] = useState<VerificationRequest | null>(null)
  const registerSchema = useMemo(
    () => createRegisterSchema(t("passwordTooShort")),
    [t]
  )
  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: "", password: "", display_name: "" },
  })

  async function onSubmit(values: RegisterValues) {
    try {
      await register.mutateAsync({ data: values })
    } catch (error) {
      applyApiError(
        error,
        form.setError,
        REGISTER_FIELDS,
        apiErrorMessage(error, tErrors)
      )
      return
    }
    // The account exists but cannot sign in until the emailed code is entered.
    // Registration sent one already; asking again only surfaces a failed send, and
    // otherwise answers with the cooldown left.
    setRegistered(
      await requestVerificationCode(
        (email) => requestCode.mutateAsync({ data: { email } }),
        values.email,
        values.password
      )
    )
  }

  return { form, onSubmit, registered }
}
