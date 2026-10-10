import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"

import { OTP_LENGTH, OtpCodeField } from "~/components/otp-code-field"
import { ResendCodeButton } from "~/components/resend-code-button"
import { Button } from "~/components/ui/button"
import { Field, FieldLabel } from "~/components/ui/field"
import { Spinner } from "~/components/ui/spinner"
import { apiErrorMessage } from "~/i18n/error-message"

/** Enter the six-digit code that was just sent, or ask for another one. */
export function CodeStep({
  id,
  description,
  submitLabel,
  onSubmit,
  onResend,
}: {
  id: string
  description: string
  submitLabel: string
  onSubmit: (code: string) => Promise<void>
  onResend: () => Promise<void>
}) {
  const { t } = useTranslation("common")
  const { t: tErrors } = useTranslation("errors")
  const [code, setCode] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (code.length !== OTP_LENGTH) {
      setError(t("code.incomplete"))
      return
    }
    setPending(true)
    setError(null)
    try {
      await onSubmit(code)
    } catch (caught) {
      setError(apiErrorMessage(caught, tErrors))
      setCode("")
    } finally {
      setPending(false)
    }
  }

  return (
    <form
      noValidate
      onSubmit={(event) => void submit(event)}
      className="flex flex-col gap-6"
    >
      <p className="text-sm text-muted-foreground">{description}</p>
      <Field data-invalid={error !== null}>
        <FieldLabel htmlFor={id}>{t("code.label")}</FieldLabel>
        <OtpCodeField
          id={id}
          value={code}
          onChange={setCode}
          invalid={error !== null}
        />
      </Field>
      {error === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" disabled={pending}>
        {pending ? <Spinner /> : null}
        {submitLabel}
      </Button>
      <ResendCodeButton onResend={onResend} />
    </form>
  )
}
