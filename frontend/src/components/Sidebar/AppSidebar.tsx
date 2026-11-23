import { Home, Users } from "lucide-react"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
} from "@/components/ui/sidebar"
import { moduleNavItems } from "@/features/modules/nav"
import { useModules } from "@/features/modules/useModules"
import useAuth from "@/hooks/useAuth"
import { type Item, Main } from "./Main"
import { User } from "./User"

const homeItem: Item = { icon: Home, title: "Dashboard", path: "/" }

export function AppSidebar() {
  const { user: currentUser, canManageUsers } = useAuth()

  const { isEnabled } = useModules()

  const baseItems: Item[] = [
    homeItem,
    ...moduleNavItems.filter((item) => isEnabled(item.module)),
  ]
  const items = canManageUsers
    ? [...baseItems, { icon: Users, title: "Admin", path: "/admin" }]
    : baseItems

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <Main items={items} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
