import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { useMemo, useState } from "react"
import { Controller, useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"
import { z } from "zod"

import {
  getUsersCurrentUserQueryKey,
  useAuthPhoneLogin,
  useAuthPhoneRequest,
} from "~/api/gen/endpoints"
import { CodeStep } from "~/components/code-step"
import { Button } from "~/components/ui/button"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { Spinner } from "~/components/ui/spinner"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"
import { phoneSchema } from "~/lib/phone"

const SKIP_AUTH_REDIRECT = { mutation: { meta: { skipAuthRedirect: true } } }

/** Phone sign-in; a number without an account gets one, so this also registers. */
export function PhoneLoginForm({
  nextPath,
  intent = "login",
}: {
  nextPath: string
  /** On the register page the code step reads as continuing, not signing in. */
  intent?: "login" | "register"
}) {
  const { t } = useTranslation("auth")
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const requestCode = useAuthPhoneRequest(SKIP_AUTH_REDIRECT)
  const login = useAuthPhoneLogin(SKIP_AUTH_REDIRECT)
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
        onResend={() => send(phone)}
      />
    )
  }

  const serverError = form.formState.errors.root?.server?.message
  return (
    <form
      noValidate
      onSubmit={(event) => void onSubmit(event)}
      className="flex flex-col gap-6"
    >
      <Controller
        name="phone"
        control={form.control}
        render={({ field, fieldState }) => (
          <Field data-invalid={fieldState.invalid}>
            <FieldLabel htmlFor="login-phone">{t("phone.label")}</FieldLabel>
            <Input
              {...field}
              id="login-phone"
              type="tel"
              autoComplete="tel"
              inputMode="tel"
              aria-invalid={fieldState.invalid}
            />
            <FieldError errors={[fieldState.error]} />
          </Field>
        )}
      />
      {serverError === undefined ? null : (
        <p role="alert" className="text-sm text-destructive">
          {serverError}
        </p>
      )}
      <Button type="submit" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? <Spinner /> : null}
        {t("phone.send")}
      </Button>
    </form>
  )
}
