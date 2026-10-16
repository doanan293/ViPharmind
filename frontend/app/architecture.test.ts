import { existsSync, readdirSync, readFileSync, statSync } from "node:fs"
import path from "node:path"

import { describe, expect, test } from "vitest"
import { z } from "zod"

const APP = path.resolve(import.meta.dirname)
const FEATURES = path.join(APP, "features")
const SHARED = ["api", "components", "hooks", "i18n", "lib"]
// The only allowed imports between features, all one-way. Anything else is composed in routes.
const ALLOWED_FEATURE_IMPORTS: Record<string, string[]> = {
  chat: ["conversations"],
  shell: ["auth", "conversations"],
  organizations: ["audit"],
  admin: ["auth", "chat", "audit"],
}
const IMPORT = /(?:from|import|import\(|vi\.mock\()\s*["']([^"']+)["']/g
const EXTENSIONS = [".ts", ".tsx", "/index.ts", "/index.tsx"]

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name)
    if (statSync(full).isDirectory())
      return name === "gen" ? [] : sourceFiles(full)
    return /\.tsx?$/.test(name) ? [full] : []
  })
}

function resolveImport(specifier: string, importer: string): string | null {
  let base: string
  if (specifier.startsWith("~/")) base = path.join(APP, specifier.slice(2))
  else if (specifier.startsWith("."))
    base = path.resolve(path.dirname(importer), specifier)
  else return null
  if (existsSync(base) && statSync(base).isFile()) return base
  const match = EXTENSIONS.map((ext) => base + ext).find((file) =>
    existsSync(file)
  )
  return match ?? null
}

type Layer = { kind: "shared" | "feature" | "routes" | "app"; name: string }

function layerOf(file: string): Layer {
  const [top = "", second = ""] = path.relative(APP, file).split(path.sep)
  if (top === "features") return { kind: "feature", name: second }
  if (top === "routes") return { kind: "routes", name: "routes" }
  if (SHARED.includes(top)) return { kind: "shared", name: top }
  return { kind: "app", name: top }
}

function imports(): { from: string; to: string }[] {
  return sourceFiles(APP)
    .filter((file) => !/\.test\.tsx?$/.test(file))
    .flatMap((from) =>
      [...readFileSync(from, "utf8").matchAll(IMPORT)]
        .map((match) => resolveImport(match[1] ?? "", from))
        .filter((to): to is string => to !== null && to.startsWith(APP))
        .map((to) => ({ from, to }))
    )
}

// The part of .oxlintrc.json the boundary test reads.
const OxlintConfig = z.object({
  overrides: z.array(
    z.object({
      files: z.array(z.string()),
      rules: z.object({
        "no-restricted-imports": z.tuple([
          z.string(),
          z.object({
            patterns: z.array(z.object({ group: z.array(z.string()) })),
          }),
        ]),
      }),
    })
  ),
})

const describeEdge = ({ from, to }: { from: string; to: string }) =>
  `${path.relative(APP, from)} -> ${path.relative(APP, to)}`

describe("frontend architecture", () => {
  const edges = imports()

  test("finds the imports it checks", () => {
    expect(edges.length).toBeGreaterThan(100)
  })

  test("shared code does not depend on features or routes", () => {
    const violations = edges.filter(
      (edge) =>
        layerOf(edge.from).kind === "shared" &&
        ["feature", "routes"].includes(layerOf(edge.to).kind)
    )
    expect(violations.map(describeEdge)).toEqual([])
  })

  test("features do not import routes", () => {
    const violations = edges.filter(
      (edge) =>
        layerOf(edge.from).kind === "feature" &&
        layerOf(edge.to).kind === "routes"
    )
    expect(violations.map(describeEdge)).toEqual([])
  })

  test("features import other features only in the allowed directions", () => {
    const violations = edges.filter((edge) => {
      const from = layerOf(edge.from)
      const to = layerOf(edge.to)
      return (
        from.kind === "feature" &&
        to.kind === "feature" &&
        from.name !== to.name &&
        !(ALLOWED_FEATURE_IMPORTS[from.name] ?? []).includes(to.name)
      )
    })
    expect(violations.map(describeEdge)).toEqual([])
  })

  test("every feature keeps its code in components, hooks or lib", () => {
    const misplaced = readdirSync(FEATURES).flatMap((feature) =>
      readdirSync(path.join(FEATURES, feature))
        .filter((entry) => !["components", "hooks", "lib"].includes(entry))
        .map((entry) => `features/${feature}/${entry}`)
    )
    expect(misplaced).toEqual([])
  })

  test("the oxlint boundary rules match the allowed feature imports", () => {
    const config = OxlintConfig.parse(
      JSON.parse(readFileSync(path.join(APP, "..", ".oxlintrc.json"), "utf8"))
    )
    const features = readdirSync(FEATURES)
    for (const feature of features) {
      const override = config.overrides.find((item) =>
        item.files.includes(`app/features/${feature}/**`)
      )
      expect(
        override,
        `no oxlint override for features/${feature}`
      ).toBeDefined()
      const banned = new Set(
        override?.rules["no-restricted-imports"][1].patterns
          .flatMap((pattern) => pattern.group)
          .filter(
            (group) => group.startsWith("~/features/") && !group.endsWith("/**")
          )
          .map((group) => group.slice("~/features/".length))
      )
      const expected = features.filter(
        (other) =>
          other !== feature &&
          !(ALLOWED_FEATURE_IMPORTS[feature] ?? []).includes(other)
      )
      expect([...banned].sort(), `features/${feature}`).toEqual(expected.sort())
    }
  })
})

const TESTS = path.join(APP, "..", "tests")
const TEST_FILE = /\.test\.tsx?$/

function allFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name)
    return statSync(full).isDirectory() ? allFiles(full) : [full]
  })
}

describe("frontend test placement", () => {
  test("every test file sits in app/ next to the code it tests", () => {
    const misplaced = sourceFiles(APP)
      .filter((file) => TEST_FILE.test(file))
      .filter(
        (file) =>
          !readdirSync(path.dirname(file)).some(
            (name) => /\.tsx?$/.test(name) && !TEST_FILE.test(name)
          )
      )
    expect(misplaced.map((file) => path.relative(APP, file))).toEqual([])
  })

  test("tests/ holds only support code and Playwright e2e specs", () => {
    const stray = allFiles(TESTS).filter(
      (file) =>
        TEST_FILE.test(file) ||
        (/\.e2e\.ts$/.test(file) &&
          path.dirname(file) !== path.join(TESTS, "e2e"))
    )
    expect(stray.map((file) => path.relative(TESTS, file))).toEqual([])
  })
})
