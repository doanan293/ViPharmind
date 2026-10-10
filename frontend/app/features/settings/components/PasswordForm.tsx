import { zodResolver } from "@hookform/resolvers/zod"
import { useMemo } from "react"
import { Controller, useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"

import { useAccountPasswordChange } from "~/api/gen/endpoints"
import { isApiError } from "~/api/problem"
import { Button } from "~/components/ui/button"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"

import { createPasswordSchema } from "../lib/account-schemas"

const PASSWORD_FIELDS = ["password", "current_password"] as const

export function PasswordForm({
  passwordSet,
  hasVerifiedEmail,
}: {
  passwordSet: boolean
  /** Passwords sign in by email, so without a verified one they do nothing yet. */
  hasVerifiedEmail: boolean
}) {
  const { t } = useTranslation("settings")
  const { t: tErrors } = useTranslation("errors")
  const change = useAccountPasswordChange()
  const schema = useMemo(
    () =>
      createPasswordSchema(
        {
          tooShort: t("password.tooShort"),
          tooLong: t("password.tooLong"),
          mismatch: t("password.mismatch"),
          currentRequired: t("password.currentRequired"),
        },
        passwordSet
      ),
    [t, passwordSet]
  )
  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues: { current_password: "", password: "", confirm: "" },
  })
  const rootError = form.formState.errors.root?.server?.message

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await change.mutateAsync({
        data: {
          current_password: passwordSet ? values.current_password : null,
          new_password: values.password,
        },
      })
      form.reset({ current_password: "", password: "", confirm: "" })
      toast.add({ type: "success", title: t("password.saved") })
    } catch (error: unknown) {
      if (isApiError(error) && error.code === "CURRENT_PASSWORD_INVALID") {
        form.setError("current_password", {
          type: "server",
          message: apiErrorMessage(error, tErrors),
        })
        return
      }
      if (isApiError(error) && error.code === "PASSWORD_INVALID") {
        form.setError("password", {
          type: "server",
          message: apiErrorMessage(error, tErrors),
        })
        return
      }
      applyApiError(
        error,
        form.setError,
        PASSWORD_FIELDS,
        apiErrorMessage(error, tErrors)
      )
    }
  })

  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        void onSubmit(event)
      }}
    >
      {hasVerifiedEmail ? null : (
        <p className="text-sm text-muted-foreground">
          {t("password.needsEmail")}
        </p>
      )}
      {passwordSet ? (
        <Controller
          control={form.control}
          name="current_password"
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor="settings-current-password">
                {t("password.current")}
              </FieldLabel>
              <Input
                {...field}
                id="settings-current-password"
                type="password"
                autoComplete="current-password"
                aria-invalid={fieldState.invalid}
              />
              <FieldError errors={[fieldState.error]} />
            </Field>
          )}
        />
      ) : null}
      <Controller
        control={form.control}
        name="password"
        render={({ field, fieldState }) => (
          <Field data-invalid={fieldState.invalid}>
            <FieldLabel htmlFor="settings-new-password">
              {t("password.new")}
            </FieldLabel>
            <Input
              {...field}
              id="settings-new-password"
              type="password"
              autoComplete="new-password"
              aria-invalid={fieldState.invalid}
            />
            <FieldError errors={[fieldState.error]} />
          </Field>
        )}
      />
      <Controller
        control={form.control}
        name="confirm"
        render={({ field, fieldState }) => (
          <Field data-invalid={fieldState.invalid}>
            <FieldLabel htmlFor="settings-confirm-password">
              {t("password.confirm")}
            </FieldLabel>
            <Input
              {...field}
              id="settings-confirm-password"
              type="password"
              autoComplete="new-password"
              aria-invalid={fieldState.invalid}
            />
            <FieldError errors={[fieldState.error]} />
          </Field>
        )}
      />
      {rootError === undefined ? null : <FieldError>{rootError}</FieldError>}
      <Button type="submit" className="self-start" disabled={change.isPending}>
        {t("password.submit")}
      </Button>
    </form>
  )
}
