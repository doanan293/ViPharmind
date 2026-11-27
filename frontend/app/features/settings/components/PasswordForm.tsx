import { zodResolver } from "@hookform/resolvers/zod"
import { useMemo } from "react"
import {
  type Control,
  Controller,
  type UseFormSetError,
  useForm,
} from "react-hook-form"
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

type PasswordValues = {
  current_password: string
  password: string
  confirm: string
}

const EMPTY_VALUES: PasswordValues = {
  current_password: "",
  password: "",
  confirm: "",
}

/** Error codes the server reports on one field rather than on the whole form. */
const FIELD_ERROR_CODES = new Map<string, keyof PasswordValues>([
  ["CURRENT_PASSWORD_INVALID", "current_password"],
  ["PASSWORD_INVALID", "password"],
])

/** Puts a rejected change on the field it concerns, or on the form when none fits. */
function applyPasswordError(
  error: unknown,
  setError: UseFormSetError<PasswordValues>,
  message: string
) {
  const field = isApiError(error)
    ? FIELD_ERROR_CODES.get(error.code)
    : undefined
  if (field !== undefined) {
    setError(field, { type: "server", message })
    return
  }
  applyApiError(error, setError, PASSWORD_FIELDS, message)
}

/** One password input bound to the form, with its label and error. */
function PasswordField({
  control,
  name,
  id,
  label,
  autoComplete,
}: {
  control: Control<PasswordValues>
  name: keyof PasswordValues
  id: string
  label: string
  autoComplete: string
}) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid}>
          <FieldLabel htmlFor={id}>{label}</FieldLabel>
          <Input
            {...field}
            id={id}
            type="password"
            autoComplete={autoComplete}
            aria-invalid={fieldState.invalid}
          />
          <FieldError errors={[fieldState.error]} />
        </Field>
      )}
    />
  )
}

/** Form state and submit handler for setting or changing the account password. */
function usePasswordForm(passwordSet: boolean) {
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
  const form = useForm<PasswordValues>({
    resolver: zodResolver(schema),
    defaultValues: EMPTY_VALUES,
  })

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await change.mutateAsync({
        data: {
          current_password: passwordSet ? values.current_password : null,
          new_password: values.password,
        },
      })
      form.reset(EMPTY_VALUES)
      toast.add({ type: "success", title: t("password.saved") })
    } catch (error: unknown) {
      applyPasswordError(error, form.setError, apiErrorMessage(error, tErrors))
    }
  })

  return { form, onSubmit, isPending: change.isPending }
}

/** Sets a first password or changes the current one; the current password is asked once set. */
export function PasswordForm({
  passwordSet,
  hasVerifiedEmail,
}: {
  passwordSet: boolean
  /** Passwords sign in by email, so without a verified one they do nothing yet. */
  hasVerifiedEmail: boolean
}) {
  const { t } = useTranslation("settings")
  const { form, onSubmit, isPending } = usePasswordForm(passwordSet)
  const rootError = form.formState.errors.root?.server?.message

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
        <PasswordField
          control={form.control}
          name="current_password"
          id="settings-current-password"
          label={t("password.current")}
          autoComplete="current-password"
        />
      ) : null}
      <PasswordField
        control={form.control}
        name="password"
        id="settings-new-password"
        label={t("password.new")}
        autoComplete="new-password"
      />
      <PasswordField
        control={form.control}
        name="confirm"
        id="settings-confirm-password"
        label={t("password.confirm")}
        autoComplete="new-password"
      />
      {rootError === undefined ? null : <FieldError>{rootError}</FieldError>}
      <Button type="submit" className="self-start" disabled={isPending}>
        {t("password.submit")}
      </Button>
    </form>
  )
}
