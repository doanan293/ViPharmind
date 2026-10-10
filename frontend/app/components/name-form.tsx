import { zodResolver } from "@hookform/resolvers/zod"
import { Controller, useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"

import { Button } from "~/components/ui/button"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { Spinner } from "~/components/ui/spinner"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"

/**
 * One required, trimmed name field with react-hook-form, zod and shadcn field: used to create
 * or rename organizations and collections. A rejected request shows on the field.
 */
export function NameForm({
  id,
  field: name,
  label,
  submitLabel,
  requiredMessage,
  maxLength,
  defaultValue = "",
  onSubmit,
  onCancel,
  cancelLabel,
  hideLabel = false,
}: {
  id: string
  /** The request body's field, so 422 items land on the input. */
  field: string
  label: string
  submitLabel: string
  requiredMessage: string
  maxLength: number
  defaultValue?: string
  onSubmit: (value: string) => Promise<unknown>
  onCancel?: () => void
  cancelLabel?: string
  hideLabel?: boolean
}) {
  const { t: tErrors } = useTranslation("errors")
  const schema = z.object({
    value: z.string().trim().min(1, requiredMessage).max(maxLength),
  })
  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues: { value: defaultValue },
  })
  const serverError = form.formState.errors.root?.server?.message

  async function submit({ value }: { value: string }) {
    try {
      await onSubmit(value)
      if (defaultValue === "") form.reset({ value: "" })
    } catch (error) {
      const message = apiErrorMessage(error, tErrors)
      applyApiError(
        error,
        (field, error_) =>
          form.setError(field === name ? "value" : "root.server", error_),
        [name],
        message
      )
    }
  }

  return (
    <form
      noValidate
      onSubmit={form.handleSubmit(submit)}
      className="flex flex-col gap-3 sm:flex-row sm:items-start"
    >
      <Controller
        name="value"
        control={form.control}
        render={({ field, fieldState }) => (
          <Field className="flex-1" data-invalid={fieldState.invalid}>
            <FieldLabel
              htmlFor={id}
              className={hideLabel ? "sr-only" : undefined}
            >
              {label}
            </FieldLabel>
            <Input
              {...field}
              id={id}
              maxLength={maxLength}
              aria-invalid={fieldState.invalid}
            />
            <FieldError errors={[fieldState.error]} />
            {serverError === undefined ? null : (
              <FieldError>{serverError}</FieldError>
            )}
          </Field>
        )}
      />
      <div className={hideLabel ? "flex gap-2" : "flex gap-2 sm:mt-6"}>
        <Button type="submit" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? <Spinner /> : null}
          {submitLabel}
        </Button>
        {onCancel === undefined ? null : (
          <Button type="button" variant="outline" onClick={onCancel}>
            {cancelLabel}
          </Button>
        )}
      </div>
    </form>
  )
}
