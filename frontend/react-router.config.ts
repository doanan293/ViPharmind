import type { Config } from "@react-router/dev/config"
import { vercelPreset } from "@vercel/react-router/vite"

export default {
  ssr: true,
  prerender: ["/", "/en", "/privacy", "/en/privacy", "/terms", "/en/terms"],
  // Vercel sets VERCEL=1 during its build. The preset splits the server build per route
  // config, which `react-router-serve`, the Dockerfile and the E2E run do not expect.
  presets: process.env.VERCEL === "1" ? [vercelPreset()] : [],
} satisfies Config
