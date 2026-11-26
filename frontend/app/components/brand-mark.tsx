import { useTranslation } from "react-i18next"

import { cn } from "~/lib/utils"

/** The ViPharmind logo: a capsule on the brand colour, with or without the product name. */
export function BrandMark({
  withName = true,
  className,
}: {
  withName?: boolean
  className?: string
}) {
  const { t } = useTranslation("common")
  const name = t("appName")
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <svg
        viewBox="0 0 32 32"
        className="size-7! shrink-0"
        {...(withName
          ? { "aria-hidden": true }
          : { role: "img", "aria-label": name })}
      >
        <rect width="32" height="32" rx="9" className="fill-primary" />
        <g transform="rotate(-40 16 16)" className="stroke-primary-foreground">
          <rect
            x="7"
            y="12"
            width="18"
            height="8"
            rx="4"
            fill="none"
            strokeWidth="2.4"
          />
          <line x1="16" y1="12" x2="16" y2="20" strokeWidth="2.4" />
        </g>
      </svg>
      {withName ? (
        <span className="text-base font-semibold tracking-tight">
          Vi<span className="text-primary">Pharm</span>ind
        </span>
      ) : null}
    </span>
  )
}
