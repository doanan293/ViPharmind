import { type Control, Controller } from "react-hook-form"
import { useTranslation } from "react-i18next"

import { DocumentKind } from "~/api/gen/schemas"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { NativeSelect, NativeSelectOption } from "~/components/ui/native-select"

import {
  DOCUMENT_TITLE_MAX_LENGTH,
  type DocumentValues,
  SOURCE_TITLE_MAX_LENGTH,
} from "../lib/document-form"

type TextFieldName = "title" | "source_title" | "source_url"

function TextField({
  control,
  name,
  id,
  label,
  inputProps,
}: {
  control: Control<DocumentValues>
  name: TextFieldName
  id: string
  label: string
  inputProps: { maxLength?: number; type?: string }
}) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid}>
          <FieldLabel htmlFor={id}>{label}</FieldLabel>
          <Input
            {...field}
            {...inputProps}
            id={id}
            aria-invalid={fieldState.invalid}
          />
          <FieldError errors={[fieldState.error]} />
        </Field>
      )}
    />
  )
}

function KindField({ control }: { control: Control<DocumentValues> }) {
  const { t } = useTranslation("collections")
  return (
    <Controller
      name="kind"
      control={control}
      render={({ field }) => (
        <Field>
          <FieldLabel htmlFor="document-kind">{t("editor.kind")}</FieldLabel>
          <NativeSelect
            id="document-kind"
            value={field.value}
            onBlur={field.onBlur}
            onChange={(event) => {
              const kind = Object.values(DocumentKind).find(
                (value) => value === event.target.value
              )
              if (kind !== undefined) field.onChange(kind)
            }}
          >
            {Object.values(DocumentKind).map((kind) => (
              <NativeSelectOption key={kind} value={kind}>
                {t(`editor.kindValue.${kind}`)}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Field>
      )}
    />
  )
}

/**
 * The document editor's title, kind, source title and source URL fields, in
 * that order. Render them inside a `FieldGroup` of the editor's form.
 */
export function DocumentMetaFields({
  control,
}: {
  control: Control<DocumentValues>
}) {
  const { t } = useTranslation("collections")
  return (
    <>
      <TextField
        control={control}
        name="title"
        id="document-title"
        label={t("editor.title")}
        inputProps={{ maxLength: DOCUMENT_TITLE_MAX_LENGTH }}
      />
      <KindField control={control} />
      <TextField
        control={control}
        name="source_title"
        id="document-source"
        label={t("editor.source")}
        inputProps={{ maxLength: SOURCE_TITLE_MAX_LENGTH }}
      />
      <TextField
        control={control}
        name="source_url"
        id="document-source-url"
        label={t("editor.sourceUrl")}
        inputProps={{ type: "url" }}
      />
    </>
  )
}
