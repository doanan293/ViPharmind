import type { Role } from "~/api/gen/schemas"

const ROLE_RANK: Record<Role, number> = { member: 0, editor: 1, owner: 2 }

export type Viewer = { role: Role | null; superadmin: boolean }

export function atLeast(viewer: Viewer, role: Role): boolean {
  return (
    viewer.superadmin ||
    (viewer.role !== null && ROLE_RANK[viewer.role] >= ROLE_RANK[role])
  )
}

/** Mirrors backend domain/access/policy.invitable_roles. */
export function invitableRoles(viewer: Viewer): Role[] {
  if (viewer.superadmin || viewer.role === "owner") {
    return ["member", "editor", "owner"]
  }
  if (viewer.role === "editor") {
    return ["member", "editor"]
  }
  return viewer.role === "member" ? ["member"] : []
}
