const DEFAULT_NEXT_PATH = "/chat"

/** First code point after the C0 control range. */
const FIRST_PRINTABLE_CODE = 0x20
/** The DEL control character. */
const DELETE_CODE = 0x7f

/** C0 controls and DEL. URL parsing drops tabs and newlines, so `/\t/x` would become `//x`. */
function hasControlCharacter(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index)
    if (code < FIRST_PRINTABLE_CODE || code === DELETE_CODE) return true
  }
  return false
}

/** Accept only same-origin paths so `next` cannot send the user to another site. */
export function safeNextPath(value: string | null | undefined): string {
  if (
    value === null ||
    value === undefined ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.startsWith("/\\") ||
    hasControlCharacter(value)
  ) {
    return DEFAULT_NEXT_PATH
  }
  return value
}
