import { describe, expect, test } from "vitest"

import { atLeast, invitableRoles } from "./roles"

describe("roles", () => {
  test("ranks roles and lets superadmins through", () => {
    expect(atLeast({ role: "editor", superadmin: false }, "editor")).toBe(true)
    expect(atLeast({ role: "member", superadmin: false }, "editor")).toBe(false)
    expect(atLeast({ role: null, superadmin: true }, "owner")).toBe(true)
    expect(atLeast({ role: null, superadmin: false }, "member")).toBe(false)
  })

  test("invitable roles follow the backend policy", () => {
    expect(invitableRoles({ role: "owner", superadmin: false })).toEqual([
      "member",
      "editor",
      "owner",
    ])
    expect(invitableRoles({ role: "editor", superadmin: false })).toEqual([
      "member",
      "editor",
    ])
    expect(invitableRoles({ role: "member", superadmin: false })).toEqual([
      "member",
    ])
    expect(invitableRoles({ role: null, superadmin: false })).toEqual([])
  })
})
