import { Link, useLocation } from "react-router"

import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "~/components/ui/sidebar"

/** One sidebar link: its label, target path and optional icon. */
export interface NavItem {
  title: string
  url: string
  icon?: React.ReactNode
}

/**
 * Whether the sidebar link to `url` is the current page: the path itself or any page below
 * it.
 */
export function isActivePath(pathname: string, url: string): boolean {
  return pathname === url || pathname.startsWith(`${url}/`)
}

/**
 * The main sidebar links, the current page highlighted; a collapsed sidebar shows the
 * label as a tooltip.
 */
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
