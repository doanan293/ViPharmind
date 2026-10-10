import { zodResolver } from "@hookform/resolvers/zod"
import { useMemo, useState } from "react"
import { Controller, useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"
import { z } from "zod"

import {
  useAuthPasswordForgot,
  useAuthPasswordReset,
} from "~/api/gen/endpoints"
import { OTP_LENGTH, OtpCodeField } from "~/components/otp-code-field"
import { ResendCodeButton } from "~/components/resend-code-button"
import { Button } from "~/components/ui/button"
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { Spinner } from "~/components/ui/spinner"
import { toast } from "~/components/ui/toast"
import { passwordSchema } from "~/features/auth/lib/password"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"

const SKIP_AUTH_REDIRECT = { mutation: { meta: { skipAuthRedirect: true } } }

export function ForgotPasswordForm() {
  const { t } = useTranslation("auth")
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const forgot = useAuthPasswordForgot(SKIP_AUTH_REDIRECT)
  const reset = useAuthPasswordReset(SKIP_AUTH_REDIRECT)
  const [email, setEmail] = useState<string | null>(null)

  const emailForm = useForm({
    resolver: zodResolver(z.object({ email: z.email() })),
    defaultValues: { email: "" },
  })
  const resetSchema = useMemo(
    () =>
      z
        .object({
          code: z
            .string()
            .length(OTP_LENGTH, { error: t("forgot.codeIncomplete") }),
          password: passwordSchema(t("passwordTooShort")),
          confirm: z.string(),
        })
        .refine((values) => values.password === values.confirm, {
          error: t("forgot.mismatch"),
          path: ["confirm"],
        }),
    [t]
  )
  const resetForm = useForm({
    resolver: zodResolver(resetSchema),
    defaultValues: { code: "", password: "", confirm: "" },
  })

  const sendCode = emailForm.handleSubmit(async (values) => {
    try {
      await forgot.mutateAsync({ data: { email: values.email } })
      setEmail(values.email)
    } catch (error) {
      applyApiError(
        error,
        emailForm.setError,
        ["email"],
        apiErrorMessage(error, tErrors)
      )
    }
  })

  const submitReset = resetForm.handleSubmit(async (values) => {
    if (email === null) {
      return
    }
    try {
      await reset.mutateAsync({
        data: { email, code: values.code, password: values.password },
      })
    } catch (error) {
      applyApiError(
        error,
        resetForm.setError,
        ["password"],
        apiErrorMessage(error, tErrors)
      )
      return
    }
    toast.add({ type: "success", title: t("forgot.done") })
    await navigate("/login", { replace: true })
  })

  if (email === null) {
    const serverError = emailForm.formState.errors.root?.server?.message
    return (
      <form
        noValidate
        onSubmit={(event) => void sendCode(event)}
        className="flex flex-col gap-6"
      >
        <Controller
          name="email"
          control={emailForm.control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor="forgot-email">{t("email")}</FieldLabel>
              <Input
                {...field}
                id="forgot-email"
                type="email"
                autoComplete="email"
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
        <Button type="submit" disabled={emailForm.formState.isSubmitting}>
          {emailForm.formState.isSubmitting ? <Spinner /> : null}
          {t("phone.send")}
        </Button>
      </form>
    )
  }

  const serverError = resetForm.formState.errors.root?.server?.message
  return (
    <form
      noValidate
      onSubmit={(event) => void submitReset(event)}
      className="flex flex-col gap-6"
    >
      <p className="text-sm text-muted-foreground">
        {t("forgot.sentTo", { email })}
      </p>
      <FieldGroup>
        <Controller
          name="code"
          control={resetForm.control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor="forgot-code">{t("forgot.code")}</FieldLabel>
              <OtpCodeField
                id="forgot-code"
                value={field.value}
                onChange={field.onChange}
                invalid={fieldState.invalid}
              />
              <FieldError errors={[fieldState.error]} />
            </Field>
          )}
        />
        {(["password", "confirm"] as const).map((name) => (
          <Controller
            key={name}
            name={name}
            control={resetForm.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor={`forgot-${name}`}>
                  {t(`forgot.${name}`)}
                </FieldLabel>
                <Input
                  {...field}
                  id={`forgot-${name}`}
                  type="password"
                  autoComplete="new-password"
                  aria-invalid={fieldState.invalid}
                />
                <FieldError errors={[fieldState.error]} />
              </Field>
            )}
          />
        ))}
      </FieldGroup>
      {serverError === undefined ? null : (
        <p role="alert" className="text-sm text-destructive">
          {serverError}
        </p>
      )}
      <Button type="submit" disabled={resetForm.formState.isSubmitting}>
        {resetForm.formState.isSubmitting ? <Spinner /> : null}
        {t("forgot.submit")}
      </Button>
      <ResendCodeButton
        onResend={async () => {
          await forgot.mutateAsync({ data: { email } })
        }}
      />
    </form>
  )
}
