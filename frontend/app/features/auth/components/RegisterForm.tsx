import { useTranslation } from "react-i18next"

import { FieldGroup } from "~/components/ui/field"
import {
  FormSubmit,
  FormTextField,
} from "~/features/auth/components/FormFields"
import { VerifyEmailStep } from "~/features/auth/components/VerifyEmailStep"
import { useRegisterForm } from "~/features/auth/hooks/use-register-form"

/** Email registration; the new account is verified with an emailed code, then signed in. */
export function RegisterForm({ nextPath }: { nextPath: string }) {
  const { t } = useTranslation("auth")
  const { form, onSubmit, registered } = useRegisterForm()

  if (registered !== null) {
    return <VerifyEmailStep request={registered} nextPath={nextPath} />
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
          name="display_name"
          id="register-display-name"
          label={t("displayName")}
          autoComplete="name"
        />
        <FormTextField
          control={form.control}
          name="email"
          id="register-email"
          label={t("email")}
          type="email"
          autoComplete="email"
        />
        <FormTextField
          control={form.control}
          name="password"
          id="register-password"
          label={t("password")}
          type="password"
          autoComplete="new-password"
        />
      </FieldGroup>
      <FormSubmit
        serverError={form.formState.errors.root?.server?.message}
        isSubmitting={form.formState.isSubmitting}
        label={t("register.submit")}
      />
    </form>
  )
}
