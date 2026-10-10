import { useParams } from "react-router"

import { AdminPage } from "~/features/admin/components/AdminPage"
import { requireSuperadmin } from "~/features/admin/lib/require-superadmin"

import type { Route } from "./+types/admin"

export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  return { user: await requireSuperadmin(request) }
}

export default function AdminRoute() {
  const { section } = useParams()
  return <AdminPage section={section} />
}
