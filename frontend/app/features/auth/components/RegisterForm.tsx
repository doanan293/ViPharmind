import { zodResolver } from "@hookform/resolvers/zod"
import { Controller, useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { useMemo, useState } from "react"
import { z } from "zod"

import {
  useAuthEmailVerifyRequest,
  useRegisterRegister,
} from "~/api/gen/endpoints"
import { RegisterRegisterBody } from "~/api/gen/zod"
import { Button } from "~/components/ui/button"
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { Spinner } from "~/components/ui/spinner"
import {
  type VerificationRequest,
  VerifyEmailStep,
  requestVerificationCode,
} from "~/features/auth/components/VerifyEmailStep"
import { passwordSchema } from "~/features/auth/lib/password"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"

/** Built per render language so the password message is translated. */
function createRegisterSchema(passwordTooShort: string) {
  return RegisterRegisterBody.pick({
    email: true,
    password: true,
    display_name: true,
  }).extend({
    password: passwordSchema(passwordTooShort),
    display_name: z.string().trim().max(100),
  })
}

type RegisterValues = z.infer<ReturnType<typeof createRegisterSchema>>

const REGISTER_FIELDS = ["email", "password", "display_name"] as const

export function RegisterForm({ nextPath }: { nextPath: string }) {
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

  if (registered !== null) {
    return <VerifyEmailStep request={registered} nextPath={nextPath} />
  }

  const serverError = form.formState.errors.root?.server?.message

  return (
    <form
      noValidate
      onSubmit={form.handleSubmit(onSubmit)}
      className="flex flex-col gap-6"
    >
      <FieldGroup>
        <Controller
          name="display_name"
          control={form.control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor="register-display-name">
                {t("displayName")}
              </FieldLabel>
              <Input
                {...field}
                id="register-display-name"
                autoComplete="name"
                aria-invalid={fieldState.invalid}
              />
              <FieldError errors={[fieldState.error]} />
            </Field>
          )}
        />
        <Controller
          name="email"
          control={form.control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor="register-email">{t("email")}</FieldLabel>
              <Input
                {...field}
                id="register-email"
                type="email"
                autoComplete="email"
                aria-invalid={fieldState.invalid}
              />
              <FieldError errors={[fieldState.error]} />
            </Field>
          )}
        />
        <Controller
          name="password"
          control={form.control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor="register-password">
                {t("password")}
              </FieldLabel>
              <Input
                {...field}
                id="register-password"
                type="password"
                autoComplete="new-password"
                aria-invalid={fieldState.invalid}
              />
              <FieldError errors={[fieldState.error]} />
            </Field>
          )}
        />
      </FieldGroup>
      {serverError === undefined ? null : (
        <FieldError>{serverError}</FieldError>
      )}
      <Button type="submit" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? <Spinner /> : null}
        {t("register.submit")}
      </Button>
    </form>
  )
}
