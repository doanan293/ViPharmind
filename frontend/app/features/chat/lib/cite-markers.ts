const CITE_MARKER = /\[(\d{1,3})\](?!\()/g
const CITE_INDEX = /^[1-9]\d{0,2}$/

/** Replaces each complete `[n]` marker (1 to 3 digits, not a Markdown link) with a `cite-ref` element for Streamdown. */
export function toCiteRefMarkup(text: string): string {
  return text.replaceAll(
    CITE_MARKER,
    (_marker, index: string) => `<cite-ref index="${index}"></cite-ref>`
  )
}

/** Reads the `index` attribute of a `cite-ref` element as a citation number from 1 to 999, or null. */
export function parseCiteIndex(value: unknown): number | null {
  return typeof value === "string" && CITE_INDEX.test(value)
    ? Number(value)
    : null
}
