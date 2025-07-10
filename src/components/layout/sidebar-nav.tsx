
'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { SidebarMenu, SidebarMenuItem, SidebarMenuButton } from '@/components/ui/sidebar';
import { LayoutDashboard, Settings, Wifi, RotateCcw, Network, ListChecks, Smartphone, BarChart3, AreaChart, BookText } from 'lucide-react';

const navItems = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/proxy-list', label: 'Proxy List', icon: ListChecks },
  { href: '/modems', label: 'Modem Status', icon: Wifi },
  { href: '/proxies', label: 'Proxy Control', icon: Network },
  { href: '/modem-control', label: 'Modem Control', icon: Smartphone },
  { href: '/ip-rotation', label: 'IP Rotation', icon: RotateCcw },
];

const secondaryNavItems = [
    { href: '/network-stats', label: 'Network Stats', icon: AreaChart },
    { href: '/logs', label: 'System Logs', icon: BarChart3 },
    { href: '/settings', label: 'Settings', icon: Settings },
    { href: '/documentation', label: 'Documentation', icon: BookText },
];

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <SidebarMenu>
      {navItems.map((item) => {
        const Icon = item.icon;
        return (
          <SidebarMenuItem key={item.href}>
            <Link href={item.href} passHref legacyBehavior>
              <SidebarMenuButton
                asChild
                isActive={pathname === item.href}
                tooltip={{ children: item.label, className: "bg-sidebar text-sidebar-foreground" }}
              >
                <a>
                  <Icon className="h-5 w-5" />
                  <span>{item.label}</span>
                </a>
              </SidebarMenuButton>
            </Link>
          </SidebarMenuItem>
        );
      })}
       <div className="px-2">
         <hr className="my-2 border-sidebar-border" />
       </div>
      {secondaryNavItems.map((item) => {
        const Icon = item.icon;
        return (
          <SidebarMenuItem key={item.href}>
            <Link href={item.href} passHref legacyBehavior>
              <SidebarMenuButton
                asChild
                isActive={pathname === item.href}
                tooltip={{ children: item.label, className: "bg-sidebar text-sidebar-foreground" }}
              >
                <a>
                  <Icon className="h-5 w-5" />
                  <span>{item.label}</span>
                </a>
              </SidebarMenuButton>
            </Link>
          </SidebarMenuItem>
        );
      })}
    </SidebarMenu>
  );
}
