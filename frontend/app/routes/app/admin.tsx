import { useParams } from "react-router"

import { AdminPage } from "~/features/admin/components/AdminPage"
import { adminLoader } from "~/features/admin/lib/require-superadmin"

/**
 * Lets only superadmins into the console: anyone else gets a 404, so the console is not
 * advertised.
 */
export const clientLoader = adminLoader

/** The superadmin console at `/admin/:section?`; the URL segment picks the section. */
export default function AdminRoute() {
  const { section } = useParams()
  return <AdminPage section={section} />
}
