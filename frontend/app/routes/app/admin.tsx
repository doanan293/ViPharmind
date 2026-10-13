import { useParams } from "react-router"

import { AdminPage } from "~/features/admin/components/AdminPage"
import { adminLoader } from "~/features/admin/lib/require-superadmin"

export const clientLoader = adminLoader

export default function AdminRoute() {
  const { section } = useParams()
  return <AdminPage section={section} />
}
