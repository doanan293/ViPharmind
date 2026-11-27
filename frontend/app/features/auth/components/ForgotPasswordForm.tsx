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
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "~/components/ui/field"
import { toast } from "~/components/ui/toast"
import {
  FormSubmit,
  FormTextField,
} from "~/features/auth/components/FormFields"
import { passwordSchema } from "~/features/auth/lib/password"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"

const SKIP_AUTH_REDIRECT = { mutation: { meta: { skipAuthRedirect: true } } }

/** First step: asks for the account email and sends it a reset code. */
function ForgotEmailStep({ onSent }: { onSent: (email: string) => void }) {
  const { t } = useTranslation("auth")
  const { t: tErrors } = useTranslation("errors")
  const forgot = useAuthPasswordForgot(SKIP_AUTH_REDIRECT)
  const emailForm = useForm({
    resolver: zodResolver(z.object({ email: z.email() })),
    defaultValues: { email: "" },
  })

  const sendCode = emailForm.handleSubmit(async (values) => {
    try {
      await forgot.mutateAsync({ data: { email: values.email } })
      onSent(values.email)
    } catch (error) {
      applyApiError(
        error,
        emailForm.setError,
        ["email"],
        apiErrorMessage(error, tErrors)
      )
    }
  })

  return (
    <form
      noValidate
      onSubmit={(event) => void sendCode(event)}
      className="flex flex-col gap-6"
    >
      <FormTextField
        control={emailForm.control}
        name="email"
        id="forgot-email"
        label={t("email")}
        type="email"
        autoComplete="email"
      />
      <FormSubmit
        serverError={emailForm.formState.errors.root?.server?.message}
        isSubmitting={emailForm.formState.isSubmitting}
        label={t("phone.send")}
      />
    </form>
  )
}

/** The reset form's schema, built per render language so its messages are translated. */
function useResetSchema() {
  const { t } = useTranslation("auth")
  return useMemo(
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
}

/** Second step: the emailed code and the new password, twice; success goes to /login. */
function ResetPasswordStep({ email }: { email: string }) {
  const { t } = useTranslation("auth")
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const forgot = useAuthPasswordForgot(SKIP_AUTH_REDIRECT)
  const reset = useAuthPasswordReset(SKIP_AUTH_REDIRECT)
  const resetSchema = useResetSchema()
  const resetForm = useForm({
    resolver: zodResolver(resetSchema),
    defaultValues: { code: "", password: "", confirm: "" },
  })

  const submitReset = resetForm.handleSubmit(async (values) => {
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
          <FormTextField
            key={name}
            control={resetForm.control}
            name={name}
            id={`forgot-${name}`}
            label={t(`forgot.${name}`)}
            type="password"
            autoComplete="new-password"
          />
        ))}
      </FieldGroup>
      <FormSubmit
        serverError={resetForm.formState.errors.root?.server?.message}
        isSubmitting={resetForm.formState.isSubmitting}
        label={t("forgot.submit")}
      />
      <ResendCodeButton
        onResend={async () => {
          await forgot.mutateAsync({ data: { email } })
        }}
      />
    </form>
  )
}

/** Password reset by email: send a code to the address, then set a new password with it. */
export function ForgotPasswordForm() {
  const [email, setEmail] = useState<string | null>(null)
  if (email === null) {
    return <ForgotEmailStep onSent={setEmail} />
  }
  return <ResetPasswordStep email={email} />
}
