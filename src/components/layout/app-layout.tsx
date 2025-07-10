import type { PropsWithChildren } from 'react';
import { SidebarProvider, Sidebar, SidebarHeader, SidebarContent, SidebarFooter, SidebarInset, SidebarTrigger } from '@/components/ui/sidebar';
import { SidebarNav } from './sidebar-nav';
import { Button } from '@/components/ui/button';
import { LogOut, Moon, Sun } from 'lucide-react';
// import { useTheme } from 'next-themes'; // For theme toggle if needed later

export function AppLayout({ children }: PropsWithChildren) {
  // const { setTheme, theme } = useTheme(); // For theme toggle if needed later

  return (
    <SidebarProvider defaultOpen>
      <Sidebar className="border-r" collapsible="icon">
        <SidebarHeader className="p-4">
          <div className="flex items-center gap-2 group-data-[collapsible=icon]:justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8 text-primary">
              <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/>
              <path d="M12 18a2 2 0 0 0 2-2h-4a2 2 0 0 0 2 2z"/>
              <path d="M12 6v1m0 1m0 1m0 1m0 1m0 1"/>
              <path d="M8.793 8.793l.707.707m4.707 4.707l.707.707m0-5.414l-.707.707m-4.707 4.707l-.707.707"/>
            </svg>
            <h1 className="text-2xl font-semibold text-foreground group-data-[collapsible=icon]:hidden">Proxy Pilot</h1>
          </div>
        </SidebarHeader>
        <SidebarContent className="p-2">
          <SidebarNav />
        </SidebarContent>
        <SidebarFooter className="p-4 mt-auto group-data-[collapsible=icon]:p-2">
          {/* <Button
            variant="ghost"
            size="icon"
            className="w-full group-data-[collapsible=icon]:w-auto"
            onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
            aria-label="Toggle theme"
          >
            <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
            <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
          </Button> */}
          <Button variant="ghost" className="w-full group-data-[collapsible=icon]:aspect-square group-data-[collapsible=icon]:p-0">
            <LogOut className="mr-2 h-5 w-5 group-data-[collapsible=icon]:mr-0" />
            <span className="group-data-[collapsible=icon]:hidden">Logout</span>
          </Button>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset>
        <header className="sticky top-0 z-10 flex items-center justify-between h-16 px-6 bg-background/80 backdrop-blur-sm border-b">
          <SidebarTrigger />
          <span className="font-semibold">Welcome to Proxy Pilot</span>
        </header>
        <main className="flex-1 p-6 overflow-auto">
          {children}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
