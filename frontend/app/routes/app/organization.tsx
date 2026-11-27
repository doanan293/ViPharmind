import { useParams } from "react-router"

import { OrganizationPage } from "~/features/organizations/components/OrganizationPage"

/**
 * One organization at `/organizations/:organizationId/:tab?`; the page remounts when the
 * organization changes.
 */
export default function OrganizationRoute() {
  const { organizationId = "", tab } = useParams()
  return (
    <OrganizationPage
      key={organizationId}
      organizationId={organizationId}
      tab={tab}
    />
  )
}
