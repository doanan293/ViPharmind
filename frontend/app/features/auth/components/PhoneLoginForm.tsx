import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { useMemo, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"
import { z } from "zod"

import {
  getUsersCurrentUserQueryKey,
  useAuthPhoneLogin,
  useAuthPhoneRequest,
} from "~/api/gen/endpoints"
import { CodeStep } from "~/components/code-step"
import {
  FormSubmit,
  FormTextField,
} from "~/features/auth/components/FormFields"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"
import { phoneSchema } from "~/lib/phone"

const SKIP_AUTH_REDIRECT = { mutation: { meta: { skipAuthRedirect: true } } }

type Intent = "login" | "register"

/** The SMS code step: a correct code signs in (or registers) and goes to `nextPath`. */
function PhoneCodeStep({
  phone,
  nextPath,
  intent,
  onResend,
}: {
  phone: string
  nextPath: string
  intent: Intent
  onResend: () => Promise<void>
}) {
  const { t } = useTranslation("auth")
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const login = useAuthPhoneLogin(SKIP_AUTH_REDIRECT)
  return (
    <CodeStep
      id="phone-login-code"
      description={t("phone.sentTo", { phone })}
      submitLabel={
        intent === "register" ? t("phone.continue") : t("login.submit")
      }
      onSubmit={async (code) => {
        await login.mutateAsync({ data: { phone, code } })
        await queryClient.invalidateQueries({
          queryKey: getUsersCurrentUserQueryKey(),
        })
        await navigate(nextPath, { replace: true })
      }}
      onResend={onResend}
    />
  )
}

/** Phone sign-in; a number without an account gets one, so this also registers. */
export function PhoneLoginForm({
  nextPath,
  intent = "login",
}: {
  nextPath: string
  /** On the register page the code step reads as continuing, not signing in. */
  intent?: Intent
}) {
  const { t } = useTranslation("auth")
  const { t: tErrors } = useTranslation("errors")
  const requestCode = useAuthPhoneRequest(SKIP_AUTH_REDIRECT)
  const [phone, setPhone] = useState<string | null>(null)
  const schema = useMemo(
    () => z.object({ phone: phoneSchema(tErrors("PHONE_NUMBER_INVALID")) }),
    [tErrors]
  )
  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues: { phone: "" },
  })

  async function send(number: string): Promise<void> {
    await requestCode.mutateAsync({ data: { phone: number } })
  }

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await send(values.phone)
      setPhone(values.phone)
    } catch (error) {
      applyApiError(
        error,
        form.setError,
        ["phone"],
        apiErrorMessage(error, tErrors)
      )
    }
  })

  if (phone !== null) {
    return (
      <PhoneCodeStep
        phone={phone}
        nextPath={nextPath}
        intent={intent}
        onResend={() => send(phone)}
      />
    )
  }

  return (
    <form
      noValidate
      onSubmit={(event) => void onSubmit(event)}
      className="flex flex-col gap-6"
    >
      <FormTextField
        control={form.control}
        name="phone"
        id="login-phone"
        label={t("phone.label")}
        type="tel"
        autoComplete="tel"
        inputMode="tel"
      />
      <FormSubmit
        serverError={form.formState.errors.root?.server?.message}
        isSubmitting={form.formState.isSubmitting}
        label={t("phone.send")}
      />
    </form>
  )
}
