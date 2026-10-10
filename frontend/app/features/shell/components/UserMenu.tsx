import { LogOutIcon } from "lucide-react"
import { useTranslation } from "react-i18next"

import type { AccountView } from "~/api/gen/schemas"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "~/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "~/components/ui/sidebar"
import { useLogout } from "~/features/auth/hooks/use-logout"
import { accountLabel } from "~/features/auth/lib/account-label"

export function UserMenu({ user }: { user: AccountView }) {
  const { t } = useTranslation("common")
  const logout = useLogout()
  const displayName = accountLabel(user)

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <SidebarMenuButton size="lg" aria-label={t("userMenu.open")} />
            }
          >
            <span className="truncate">{displayName}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="start">
            <DropdownMenuGroup>
              <DropdownMenuLabel>
                {user.email ?? user.phone_number}
              </DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => {
                void logout()
              }}
            >
              <LogOutIcon aria-hidden="true" />
              {t("userMenu.logout")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
