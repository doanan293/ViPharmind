/** An exported declaration: `export [default] [declare] [async] [abstract] <kind> <name>`. */
const DECLARATION =
  /^export\s+(?:default\s+)?(?:declare\s+)?(?:async\s+)?(?:abstract\s+)?(function\*?|const|let|class|type|interface|enum)\s+([A-Za-z_$][\w$]*)/

/** The first line of the comment block that ends on line `end`. */
function openingOf(lines: string[], end: number): string {
  let start = end
  while (start > 0 && !(lines[start] ?? "").includes("/*")) {
    start -= 1
  }
  return (lines[start] ?? "").trim()
}

/** Whether a `/** … *\/` block ends right above line `index`, decorators aside. */
function documentedAbove(lines: string[], index: number): boolean {
  let above = index - 1
  while (above >= 0 && (lines[above] ?? "").trim().startsWith("@")) {
    above -= 1
  }
  const previous = (lines[above] ?? "").trim()
  return previous.endsWith("*/") && openingOf(lines, above).startsWith("/**")
}

/**
 * Lists the exported declarations of one source file that have no JSDoc comment right above
 * them, as `path:line name`. Re-exports (`export { x } from`) are not declarations.
 */
export function missingJsDoc(source: string, file: string): string[] {
  const lines = source.split("\n")
  return lines.flatMap((line, index) => {
    const match = DECLARATION.exec(line)
    if (!match || documentedAbove(lines, index)) {
      return []
    }
    return [`${file}:${index + 1} ${match[2] ?? ""}`]
  })
}
