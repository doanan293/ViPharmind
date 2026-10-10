/** Comma-separated text from a form field, as the list the API stores. */
export function parseList(text: string): string[] {
  return text
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item !== "")
}

export function formatList(items: readonly string[] | undefined): string {
  return (items ?? []).join(", ")
}
