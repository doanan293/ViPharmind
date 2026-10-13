const DEFAULT_NEXT_PATH = "/chat"

/** C0 controls and DEL. URL parsing drops tabs and newlines, so `/\t/x` would become `//x`. */
function hasControlCharacter(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index)
    if (code < 0x20 || code === 0x7f) return true
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
