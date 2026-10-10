import { zodResolver } from "@hookform/resolvers/zod"
import { Controller, useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"

import { Button } from "~/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog"
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"

export interface Quota {
  text_quota_bytes: number | null
  collection_quota: number | null
}

const count = z.union([z.literal(""), z.coerce.number().int().min(0)])

const schema = z.object({ text: count, collections: count })

type Values = z.input<typeof schema>

function toQuota(values: z.output<typeof schema>): Quota {
  return {
    text_quota_bytes: values.text === "" ? null : values.text,
    collection_quota: values.collections === "" ? null : values.collections,
  }
}

/** Sets a user's or an organization's own quota; empty fields fall back to the default. */
export function QuotaDialog({
  name,
  quota,
  open,
  onOpenChange,
  onSave,
}: {
  name: string
  quota: Quota
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (quota: Quota) => Promise<unknown>
}) {
  const { t } = useTranslation("admin")
  const { t: tErrors } = useTranslation("errors")
  const form = useForm<Values, unknown, z.output<typeof schema>>({
    resolver: zodResolver(schema),
    values: {
      text:
        quota.text_quota_bytes === null ? "" : String(quota.text_quota_bytes),
      collections:
        quota.collection_quota === null ? "" : String(quota.collection_quota),
    },
  })
  const serverError = form.formState.errors.root?.server?.message

  async function submit(values: z.output<typeof schema>) {
    try {
      await onSave(toQuota(values))
      onOpenChange(false)
    } catch (error) {
      applyApiError(error, form.setError, [], apiErrorMessage(error, tErrors))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form noValidate onSubmit={form.handleSubmit(submit)}>
          <DialogHeader>
            <DialogTitle>{t("quota.title", { name })}</DialogTitle>
            <DialogDescription>{t("quota.description")}</DialogDescription>
          </DialogHeader>
          <FieldGroup className="py-4">
            <Controller
              name="text"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="quota-text">
                    {t("quota.text")}
                  </FieldLabel>
                  <Input
                    id="quota-text"
                    inputMode="numeric"
                    placeholder={t("quota.default")}
                    name={field.name}
                    value={String(field.value)}
                    onBlur={field.onBlur}
                    onChange={field.onChange}
                    aria-invalid={fieldState.invalid}
                  />
                  <FieldError errors={[fieldState.error]} />
                </Field>
              )}
            />
            <Controller
              name="collections"
              control={form.control}
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="quota-collections">
                    {t("quota.collections")}
                  </FieldLabel>
                  <Input
                    id="quota-collections"
                    inputMode="numeric"
                    placeholder={t("quota.default")}
                    name={field.name}
                    value={String(field.value)}
                    onBlur={field.onBlur}
                    onChange={field.onChange}
                    aria-invalid={fieldState.invalid}
                  />
                  <FieldError errors={[fieldState.error]} />
                </Field>
              )}
            />
            {serverError === undefined ? null : (
              <FieldError>{serverError}</FieldError>
            )}
          </FieldGroup>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              {t("cancel")}
            </Button>
            <Button type="submit" disabled={form.formState.isSubmitting}>
              {t("quota.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
