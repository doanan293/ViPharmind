import { describe, expect, test } from "vitest"

import { AuditAction } from "~/api/gen/schemas"
import type { AuditEventView } from "~/api/gen/schemas"

import { createTestI18n } from "../../../../tests/utils/i18n"
import { describeEvent } from "./describe-event"

function event(overrides: Partial<AuditEventView>): AuditEventView {
  return {
    id: "e1",
    occurred_at: "2026-10-11T09:00:00Z",
    actor_user_id: "u1",
    actor_name: "An",
    actor_was_superadmin: false,
    action: AuditAction["organizationcreated"],
    organization_id: null,
    subject_user_id: null,
    collection_id: null,
    details: {},
    ...overrides,
  }
}

describe("describeEvent", () => {
  test("every action reads as a sentence in both languages", () => {
    for (const language of ["vi", "en"] as const) {
      const t = createTestI18n(language).getFixedT(language, "audit")
      for (const action of Object.values(AuditAction)) {
        const text = describeEvent(
          event({
            action,
            details: {
              name: "Khoa Dược",
              title: "Thuốc tim mạch",
              from: "private",
              to: "organization",
              email: "b@example.com",
              role: "editor",
              document: "Paracetamol",
              release: 2,
              entries: 3,
            },
          }),
          t
        )
        expect(text, `${language} ${action}`).not.toContain("{{")
        expect(text, `${language} ${action}`).not.toContain("action.")
        expect(text.startsWith("An"), `${language} ${action}`).toBe(true)
      }
    }
  })

  test("marks actions taken as superadmin and names unknown actors", () => {
    const t = createTestI18n("vi").getFixedT("vi", "audit")
    expect(
      describeEvent(
        event({ actor_was_superadmin: true, details: { name: "Org" } }),
        t
      )
    ).toBe("An (Quản trị viên) đã tạo tổ chức Org")
    expect(
      describeEvent(event({ actor_name: "", details: { name: "Org" } }), t)
    ).toBe("Một người dùng đã tạo tổ chức Org")
  })
})
