import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

import { useAdminAuditInfinite } from "~/api/gen/endpoints"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs"
import { AuditList } from "~/features/audit/components/AuditList"

import { AdminOverview } from "./AdminOverview"
import { CollectionsSection } from "./CollectionsSection"
import { JobsSection } from "./JobsSection"
import { OrganizationsSection } from "./OrganizationsSection"
import { UsersSection } from "./UsersSection"

const SECTIONS = [
  "users",
  "organizations",
  "collections",
  "jobs",
  "audit",
] as const
type Section = (typeof SECTIONS)[number]

function AuditSection() {
  const query = useAdminAuditInfinite(
    { limit: 50 },
    {
      query: {
        initialPageParam: undefined,
        getNextPageParam: (page) => page.next_cursor ?? undefined,
      },
    }
  )
  return <AuditList query={query} />
}

/** The superadmin console. The route guard makes it a 404 for everyone else. */
export function AdminPage({ section }: { section: string | undefined }) {
  const { t } = useTranslation("admin")
  const navigate = useNavigate()
  const current: Section = SECTIONS.find((name) => name === section) ?? "users"
  return (
    <div className="@container/main mx-auto flex w-full max-w-7xl flex-col gap-6 p-4 md:p-6">
      <title>{t("title")}</title>
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      <AdminOverview />
      <Tabs
        value={current}
        onValueChange={(value) => void navigate(`/admin/${String(value)}`)}
      >
        <TabsList>
          {SECTIONS.map((name) => (
            <TabsTrigger key={name} value={name}>
              {t(`tabs.${name}`)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="users">
          <UsersSection />
        </TabsContent>
        <TabsContent value="organizations">
          <OrganizationsSection />
        </TabsContent>
        <TabsContent value="collections">
          <CollectionsSection />
        </TabsContent>
        <TabsContent value="jobs">
          <JobsSection />
        </TabsContent>
        <TabsContent value="audit">
          <AuditSection />
        </TabsContent>
      </Tabs>
    </div>
  )
}
