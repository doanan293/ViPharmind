/**
 * Every exported declaration in `app/` carries a JSDoc comment that says what it is for
 * (docs/engineering-guide.md, "Code"). Biome has no rule for the presence of JSDoc, so this
 * test checks it. Generated code (`api/gen`) and shadcn registry files (`components/ui`) are
 * third-party code and are not checked.
 */
import { readdirSync, readFileSync, statSync } from "node:fs"
import path from "node:path"
import { describe, expect, test } from "vitest"

import { missingJsDoc } from "../tests/utils/jsdoc"

const APP = path.dirname(new URL(import.meta.url).pathname)
const SKIPPED_DIRS = ["api/gen", "components/ui"]
/** Every checked source file under `app/`, relative to it. */
function sourceFiles(dir = APP): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry)
    const rel = path.relative(APP, full)
    if (statSync(full).isDirectory()) {
      return SKIPPED_DIRS.includes(rel) ? [] : sourceFiles(full)
    }
    const checked =
      /\.(ts|tsx)$/.test(entry) &&
      !/\.test\.(ts|tsx)$/.test(entry) &&
      !entry.endsWith(".d.ts")
    return checked ? [rel] : []
  })
}

describe("missingJsDoc", () => {
  test("flags exported declarations without JSDoc", () => {
    const source = [
      "export function f() {}",
      "export const C = () => null",
      "export class K {}",
      "export type T = string",
      "export interface I {}",
      "export default function D() {}",
    ].join("\n")
    expect(missingJsDoc(source, "x.ts")).toEqual([
      "x.ts:1 f",
      "x.ts:2 C",
      "x.ts:3 K",
      "x.ts:4 T",
      "x.ts:5 I",
      "x.ts:6 D",
    ])
  })

  test("accepts JSDoc, multi-line JSDoc and decorators in between", () => {
    const source = [
      "/** Adds. */",
      "export function add() {}",
      "/**",
      " * Many lines.",
      " */",
      "export const many = 1",
      "/** A class. */",
      "@decorator",
      "export class K {}",
    ].join("\n")
    expect(missingJsDoc(source, "x.ts")).toEqual([])
  })

  test("a plain comment is not JSDoc; internals and re-exports are not checked", () => {
    const source = [
      "// plain",
      "export function f() {}",
      "/* block */",
      "export const g = 1",
      "function internal() {}",
      'export { h } from "./h"',
    ].join("\n")
    expect(missingJsDoc(source, "x.ts")).toEqual(["x.ts:2 f", "x.ts:4 g"])
  })
})

describe("frontend documentation", () => {
  test("every export in app/ has JSDoc", () => {
    const missing = sourceFiles().flatMap((file) =>
      missingJsDoc(readFileSync(path.join(APP, file), "utf8"), file)
    )
    expect(missing).toEqual([])
  })
})
