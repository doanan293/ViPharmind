import { z } from "zod"

import {
  type DocumentDetail,
  type DocumentInput,
  DocumentKind,
} from "~/api/gen/schemas"

/** Longest document the backend accepts, in characters (MAX_DOCUMENT_CHARS). */
export const MAX_DOCUMENT_CHARS = 200_000

/** Longest document title the backend accepts, in characters. */
export const DOCUMENT_TITLE_MAX_LENGTH = 200

/** Longest source title the backend accepts, in characters. */
export const SOURCE_TITLE_MAX_LENGTH = 500

/** Longest source URL the backend accepts, in characters. */
const SOURCE_URL_MAX_LENGTH = 2000

/** Form fields a problem+json response can point at, for `applyApiError`. */
export const DOCUMENT_FIELDS = [
  "title",
  "kind",
  "source_title",
  "source_url",
  "markdown",
] as const

/** The starting input of a new document. */
export const EMPTY_DOCUMENT: DocumentInput = {
  title: "",
  kind: "drug_monograph",
  source_title: "",
  source_url: null,
  markdown: "",
}

/** The document editor's form values; an empty `source_url` means none. */
export type DocumentValues = {
  title: string
  kind: DocumentKind
  source_title: string
  source_url: string
  markdown: string
}

/** Translated validation messages for {@link documentSchema}. */
export type DocumentSchemaMessages = {
  titleRequired: string
  invalidUrl: string
  contentRequired: string
  tooLong: string
}

/** The editable fields of a stored document, as an API input. */
export function inputOf(document: DocumentDetail): DocumentInput {
  return {
    title: document.title,
    kind: document.kind,
    source_title: document.source_title,
    source_url: document.source_url,
    markdown: document.markdown,
  }
}

/** Form values for an API input, with defaults filled in for missing fields. */
export function valuesOf(input: DocumentInput): DocumentValues {
  return {
    title: input.title,
    kind: input.kind ?? "drug_monograph",
    source_title: input.source_title ?? "",
    source_url: input.source_url ?? "",
    markdown: input.markdown,
  }
}

/** The API input for submitted form values; an empty source URL becomes null. */
export function inputFromValues(values: DocumentValues): DocumentInput {
  return {
    ...values,
    source_url: values.source_url === "" ? null : values.source_url,
  }
}

/** Zod schema for the document editor, mirroring the backend's limits. */
export function documentSchema(messages: DocumentSchemaMessages) {
  return z.object({
    title: z
      .string()
      .trim()
      .min(1, messages.titleRequired)
      .max(DOCUMENT_TITLE_MAX_LENGTH),
    kind: z.enum(DocumentKind),
    source_title: z.string().trim().max(SOURCE_TITLE_MAX_LENGTH),
    source_url: z.union([
      z.literal(""),
      z.url(messages.invalidUrl).max(SOURCE_URL_MAX_LENGTH),
    ]),
    markdown: z
      .string()
      .refine((text) => text.trim() !== "", messages.contentRequired)
      .refine((text) => text.length <= MAX_DOCUMENT_CHARS, {
        message: messages.tooLong,
      }),
  })
}
