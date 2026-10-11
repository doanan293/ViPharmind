import type { Config } from "@react-router/dev/config"

export default {
  ssr: true,
  prerender: ["/", "/en", "/privacy", "/en/privacy", "/terms", "/en/terms"],
} satisfies Config
