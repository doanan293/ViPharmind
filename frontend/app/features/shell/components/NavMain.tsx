import { Link, useLocation } from "react-router"

import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "~/components/ui/sidebar"

export interface NavItem {
  title: string
  url: string
  icon?: React.ReactNode
}

export function isActivePath(pathname: string, url: string): boolean {
  return pathname === url || pathname.startsWith(`${url}/`)
}

export function NavMain({ items }: { items: NavItem[] }) {
  const { pathname } = useLocation()
  return (
    <SidebarGroup>
      <SidebarGroupContent className="flex flex-col gap-2">
        <SidebarMenu>
          {items.map((item) => (
            <SidebarMenuItem key={item.title}>
              <SidebarMenuButton
                tooltip={item.title}
                render={<Link to={item.url} />}
                isActive={isActivePath(pathname, item.url)}
              >
                {item.icon}
                <span>{item.title}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}
