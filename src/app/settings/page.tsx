
import { PageHeader } from '@/components/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { TunnelTable } from '@/components/settings/tunnel-table';
import { TunnelConfigForm } from '@/components/settings/tunnel-config-form';
import { Waypoints, Cog } from 'lucide-react';

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        title="Settings & Tunnels"
        description="Manage global application settings, configure and view active tunnels."
      />
      <div className="grid gap-8">
         <Card>
            <CardHeader>
                <CardTitle className="flex items-center">
                    <Cog className="mr-2 h-6 w-6 text-primary"/>
                    Configure New Tunnel
                </CardTitle>
                <CardDescription>
                    Create a new public tunnel for an active proxy. The proxy must be in a 'running' state.
                </CardDescription>
            </CardHeader>
            <CardContent>
                <TunnelConfigForm />
            </CardContent>
         </Card>

         <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
                <Waypoints className="mr-2 h-6 w-6 text-primary"/>
                Active Tunnels
            </CardTitle>
            <CardDescription>
              View all currently active Ngrok or Cloudflare tunnels. You can also stop tunnels from the "Proxy Control" page.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <TunnelTable />
          </CardContent>
        </Card>
      </div>
    </>
  );
}
