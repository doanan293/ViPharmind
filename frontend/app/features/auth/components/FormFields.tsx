import type { ComponentProps } from "react"
import {
  type Control,
  Controller,
  type FieldPathByValue,
  type FieldValues,
} from "react-hook-form"

import { Button } from "~/components/ui/button"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { Spinner } from "~/components/ui/spinner"

/** Props of {@link FormTextField}: the react-hook-form field plus the input's own attributes. */
export type FormTextFieldProps<T extends FieldValues> = {
  control: Control<T>
  /** A string field of the form; its errors show below the input. */
  name: FieldPathByValue<T, string>
  /** The input id, also used by the label's `htmlFor`. */
  id: string
  label: string
} & Pick<ComponentProps<"input">, "type" | "autoComplete" | "inputMode">

/** A labelled text input bound to a react-hook-form string field, with its error message. */
export function FormTextField<T extends FieldValues>({
  control,
  name,
  id,
  label,
  ...inputProps
}: FormTextFieldProps<T>) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid}>
          <FieldLabel htmlFor={id}>{label}</FieldLabel>
          <Input
            {...field}
            id={id}
            {...inputProps}
            aria-invalid={fieldState.invalid}
          />
          <FieldError errors={[fieldState.error]} />
        </Field>
      )}
    />
  )
}

/** The form-level server error, when there is one, and the submit button with its spinner. */
export function FormSubmit({
  serverError,
  isSubmitting,
  label,
}: {
  /** The `root.server` error message, or undefined to show none. */
  serverError: string | undefined
  isSubmitting: boolean
  label: string
}) {
  return (
    <>
      {serverError === undefined ? null : (
        <FieldError>{serverError}</FieldError>
      )}
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? <Spinner /> : null}
        {label}
      </Button>
    </>
  )
}
