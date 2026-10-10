import { useParams } from "react-router"

import { OrganizationPage } from "~/features/organizations/components/OrganizationPage"

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
