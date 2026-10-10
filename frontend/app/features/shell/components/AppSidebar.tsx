import {
  ActivityIcon,
  BuildingIcon,
  LibraryIcon,
  MessageSquareIcon,
  PillIcon,
  SettingsIcon,
  ShieldIcon,
} from "lucide-react"
import type * as React from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router"

import type { AccountView } from "~/api/gen/schemas"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "~/components/ui/sidebar"
import { ConversationSidebar } from "~/features/conversations/components/ConversationSidebar"

import { NavMain } from "./NavMain"
import { NavSecondary } from "./NavSecondary"
import { NavUser } from "./NavUser"

/** The app-sidebar of shadcn's dashboard-01 block with this app's pages and conversations. */
export function AppSidebar({
  user,
  ...props
}: { user: AccountView } & React.ComponentProps<typeof Sidebar>) {
  const { t } = useTranslation("common")
  const main = [
    { title: t("nav.chat"), url: "/chat", icon: <MessageSquareIcon /> },
    {
      title: t("nav.organizations"),
      url: "/organizations",
      icon: <BuildingIcon />,
    },
    { title: t("nav.collections"), url: "/collections", icon: <LibraryIcon /> },
    { title: t("nav.activity"), url: "/activity", icon: <ActivityIcon /> },
  ]
  const secondary = [
    { title: t("nav.settings"), url: "/settings", icon: <SettingsIcon /> },
    ...(user.is_superadmin
      ? [{ title: t("nav.admin"), url: "/admin", icon: <ShieldIcon /> }]
      : []),
  ]
  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              className="data-[slot=sidebar-menu-button]:p-1.5!"
              render={<Link to="/chat" />}
            >
              <PillIcon className="size-5!" />
              <span className="text-base font-semibold">{t("appName")}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={main} />
        <ConversationSidebar />
        <NavSecondary items={secondary} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter>
        <NavUser account={user} />
      </SidebarFooter>
    </Sidebar>
  )
}
