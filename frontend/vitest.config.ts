import tailwindcss from "@tailwindcss/vite"
import { playwright } from "@vitest/browser-playwright"
import { searchForWorkspaceRoot } from "vite"
import { defineConfig } from "vitest/config"

export default defineConfig({
  resolve: { tsconfigPaths: true },
  server: {
    fs: {
      allow: [
        searchForWorkspaceRoot(process.cwd()),
        "../backend/tests/contract/fixtures",
      ],
    },
  },
  test: {
    // docs/engineering-guide.md, "Tests": coverage of app code is at least 90%; generated
    // code and shadcn registry files are third-party code.
    coverage: {
      provider: "v8",
      include: ["app/**/*.{ts,tsx}"],
      exclude: [
        "app/api/gen/**",
        "app/components/ui/**",
        "app/**/*.test.{ts,tsx}",
        "app/**/*.d.ts",
      ],
      // Same measure as the backend (lines); branches and functions are reported.
      thresholds: { lines: 90, statements: 90 },
    },
    projects: [
      {
        extends: true,
        test: {
          name: "unit",
          environment: "node",
          include: ["app/**/*.test.{ts,tsx}"],
          exclude: ["app/**/*.browser.test.tsx"],
          setupFiles: [
            "./tests/setup/fail-on-console.ts",
            "./tests/setup/msw-node.ts",
          ],
        },
      },
      {
        extends: true,
        plugins: [tailwindcss()],
        // The MSW service worker is served only to browser tests, never shipped from public/.
        publicDir: "tests/public",
        // Vite reuses its optimizer cache without scanning imports, so a dependency a browser
        // test imports for the first time is optimized mid-run and reloads the page. Force a
        // fresh pre-bundle that scans every browser test and setup file before tests start.
        optimizeDeps: {
          force: true,
          entries: ["app/**/*.browser.test.tsx", "tests/setup/*.ts"],
        },
        test: {
          name: "browser",
          include: ["app/**/*.browser.test.tsx"],
          setupFiles: [
            "./tests/setup/fail-on-console.ts",
            "./tests/setup/msw-browser.ts",
            "./tests/setup/styles.ts",
          ],
          browser: {
            enabled: true,
            headless: true,
            provider: playwright(),
            instances: [{ browser: "chromium" }],
          },
        },
      },
    ],
  },
})
