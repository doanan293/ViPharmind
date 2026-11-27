import { useTranslation } from "react-i18next"

import { FieldGroup } from "~/components/ui/field"
import {
  FormSubmit,
  FormTextField,
} from "~/features/auth/components/FormFields"
import { VerifyEmailStep } from "~/features/auth/components/VerifyEmailStep"
import { useLoginForm } from "~/features/auth/hooks/use-login-form"

/** Email and password sign-in; an unverified account continues with the email code step. */
export function LoginForm({ nextPath }: { nextPath: string }) {
  const { t } = useTranslation("auth")
  const { form, onSubmit, unverified } = useLoginForm(nextPath)

  if (unverified !== null) {
    return <VerifyEmailStep request={unverified} nextPath={nextPath} />
  }

  return (
    <form
      noValidate
      onSubmit={form.handleSubmit(onSubmit)}
      className="flex flex-col gap-6"
    >
      <FieldGroup>
        <FormTextField
          control={form.control}
          name="username"
          id="login-email"
          label={t("email")}
          type="email"
          autoComplete="email"
        />
        <FormTextField
          control={form.control}
          name="password"
          id="login-password"
          label={t("password")}
          type="password"
          autoComplete="current-password"
        />
      </FieldGroup>
      <FormSubmit
        serverError={form.formState.errors.root?.server?.message}
        isSubmitting={form.formState.isSubmitting}
        label={t("login.submit")}
      />
    </form>
  )
}
