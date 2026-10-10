import type { TFunction } from "i18next"

import type { AuditEventView } from "~/api/gen/schemas"

const LABELS = {
  owner: "role.owner",
  editor: "role.editor",
  member: "role.member",
  private: "visibility.private",
  organization: "visibility.organization",
  public: "visibility.public",
} as const

function isLabelled(code: string): code is keyof typeof LABELS {
  return Object.hasOwn(LABELS, code)
}

function text(value: unknown): string {
  return typeof value === "string" || typeof value === "number"
    ? String(value)
    : ""
}

/** One sentence per event, built from its action and details. */
export function describeEvent(
  event: AuditEventView,
  t: TFunction<"audit">
): string {
  const name = event.actor_name || t("actor.unknown")
  const actor = event.actor_was_superadmin
    ? t("actor.superadmin", { name })
    : name
  const details = event.details
  // Roles and visibilities arrive as codes; the sentence reads their labels.
  const label = (value: unknown): string => {
    const code = text(value)
    return isLabelled(code) ? t(LABELS[code]) : code
  }
  return t(`action.${event.action}`, {
    actor,
    name: text(details["name"]),
    title: text(details["title"]),
    email: text(details["email"]),
    document: text(details["document"]),
    release: text(details["release"]),
    role: label(details["role"]),
    from: label(details["from"]),
    to: label(details["to"]),
  })
}
