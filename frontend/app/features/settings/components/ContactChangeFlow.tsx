import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { useMemo, useState } from "react"
import { Controller, useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"

import {
  getUsersCurrentUserQueryKey,
  useAccountEmailConfirm,
  useAccountEmailRequest,
  useAccountPhoneConfirm,
  useAccountPhoneRequest,
} from "~/api/gen/endpoints"
import type { AccountView } from "~/api/gen/schemas"
import { CodeStep } from "~/components/code-step"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { Spinner } from "~/components/ui/spinner"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"
import { phoneSchema } from "~/lib/phone"

type Kind = "email" | "phone"
type Step =
  { name: "idle" } | { name: "editing" } | { name: "code"; value: string }

/** Adds or changes the email or phone number; the change applies once the code is confirmed. */
export function ContactChangeFlow({
  kind,
  current,
  verified,
}: {
  kind: Kind
  current: string | null
  verified: boolean
}) {
  const { t } = useTranslation("settings")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const requestEmail = useAccountEmailRequest()
  const confirmEmail = useAccountEmailConfirm()
  const requestPhone = useAccountPhoneRequest()
  const confirmPhone = useAccountPhoneConfirm()
  const [step, setStep] = useState<Step>({ name: "idle" })
  const schema = useMemo(
    () =>
      z.object({
        value:
          kind === "email"
            ? z.email()
            : phoneSchema(tErrors("PHONE_NUMBER_INVALID")),
      }),
    [kind, tErrors]
  )
  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues: { value: "" },
  })

  async function request(value: string): Promise<void> {
    if (kind === "email") {
      await requestEmail.mutateAsync({ data: { email: value } })
    } else {
      await requestPhone.mutateAsync({ data: { phone: value } })
    }
  }

  async function confirm(value: string, code: string): Promise<AccountView> {
    return kind === "email"
      ? await confirmEmail.mutateAsync({ data: { email: value, code } })
      : await confirmPhone.mutateAsync({ data: { phone: value, code } })
  }

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await request(values.value)
      setStep({ name: "code", value: values.value })
    } catch (error) {
      applyApiError(
        error,
        form.setError,
        ["value"],
        apiErrorMessage(error, tErrors)
      )
    }
  })

  if (step.name === "code") {
    return (
      <CodeStep
        id={`${kind}-change-code`}
        description={t(`account.${kind}.sentTo`, { value: step.value })}
        submitLabel={t("account.confirm")}
        onSubmit={async (code) => {
          const updated = await confirm(step.value, code)
          queryClient.setQueryData(getUsersCurrentUserQueryKey(), updated)
          toast.add({ type: "success", title: t(`account.${kind}.saved`) })
          setStep({ name: "idle" })
          form.reset({ value: "" })
        }}
        onResend={() => request(step.value)}
      />
    )
  }

  if (step.name === "idle") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm">
          <span>{current ?? t(`account.${kind}.none`)}</span>
          {current === null ? null : (
            <Badge variant={verified ? "secondary" : "outline"}>
              {verified ? t("account.verified") : t("account.unverified")}
            </Badge>
          )}
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => setStep({ name: "editing" })}
        >
          {current === null
            ? t(`account.${kind}.add`)
            : t(`account.${kind}.change`)}
        </Button>
      </div>
    )
  }

  const serverError = form.formState.errors.root?.server?.message
  return (
    <form
      noValidate
      onSubmit={(event) => void onSubmit(event)}
      className="flex flex-col gap-4"
    >
      <Controller
        name="value"
        control={form.control}
        render={({ field, fieldState }) => (
          <Field data-invalid={fieldState.invalid}>
            <FieldLabel htmlFor={`${kind}-new`}>
              {t(`account.${kind}.newLabel`)}
            </FieldLabel>
            <Input
              {...field}
              id={`${kind}-new`}
              type={kind === "email" ? "email" : "tel"}
              autoComplete={kind === "email" ? "email" : "tel"}
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
      <div className="flex gap-2">
        <Button type="submit" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? <Spinner /> : null}
          {t("account.sendCode")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => setStep({ name: "idle" })}
        >
          {t("account.cancel")}
        </Button>
      </div>
    </form>
  )
}
