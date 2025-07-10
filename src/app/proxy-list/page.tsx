
'use client';

import { useEffect, useState, useCallback } from 'react';
import { PageHeader } from '@/components/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { getAllModemStatuses } from '@/services/network-service';
import { getAllProxyConfigs } from '@/services/proxy-service';
import { Skeleton } from '@/components/ui/skeleton';
import { ClipboardCopy, KeyRound, ListChecks, Info, Copy, NetworkIcon, Binary, User, Lock, AlertTriangle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface FormattedProxy {
  id: string;
  name: string;
  interfaceName: string;
  proxyString: string;
  type: '3proxy';
  ipAddress: string;
  port: number;
  username?: string;
  password?: string;
}

export default function ProxyListPage() {
  const [formattedProxies, setFormattedProxies] = useState<FormattedProxy[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const { toast } = useToast();

  const fetchAndFormatProxies = useCallback(async () => {
    setIsLoading(true);
    try {
      const modemStatuses = await getAllModemStatuses();
      const proxyConfigs = await getAllProxyConfigs();

      const activeModems = new Map(modemStatuses
        .filter(m => m.status === 'connected' && m.proxyStatus === 'running')
        .map(m => [m.interfaceName, m])
      );

      const proxies: FormattedProxy[] = [];

      for (const interfaceName in proxyConfigs) {
        const config = proxyConfigs[interfaceName];
        const activeModem = activeModems.get(interfaceName);

        if (activeModem && config && config.bindIp && config.port) {
          const ip = config.bindIp;
          const port = config.port;
          const username = config.username;
          const password = config.password;
          
          let proxyString = `${ip}:${port}`;
          if (username && password) {
            proxyString += `:${username}:${password}`;
          }

          proxies.push({
            id: activeModem.id,
            name: config.customName || activeModem.name,
            interfaceName: interfaceName,
            proxyString: proxyString,
            type: '3proxy',
            ipAddress: ip,
            port: port,
            username: username,
            password: password,
          });
        }
      }

      setFormattedProxies(proxies);

    } catch (error) {
      console.error("Failed to fetch or format proxies:", error);
      toast({ title: "Error", description: "Could not load proxy list.", variant: "destructive" });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchAndFormatProxies();
  }, [fetchAndFormatProxies]);

  const handleCopyToClipboard = (text: string | number | undefined, label: string, proxyName: string) => {
    if (text === undefined || text === null) {
      toast({ title: "Nothing to Copy", description: `${label} is not set for ${proxyName}.`, variant: "destructive" });
      return;
    }
    const textToCopy = String(text);
    navigator.clipboard.writeText(textToCopy)
      .then(() => {
        toast({ title: "Copied to Clipboard", description: `${label} for ${proxyName} copied.` });
      })
      .catch(err => {
        toast({ title: "Copy Failed", description: "Could not copy to clipboard.", variant: "destructive" });
        console.error('Failed to copy: ', err);
      });
  };

  const renderContent = () => {
    if (isLoading) {
      return (
        <div className="border rounded-md p-4">
          <Skeleton className="h-8 w-full mb-4" />
          <Skeleton className="h-10 w-full mb-2" />
          <Skeleton className="h-10 w-full mb-2" />
          <Skeleton className="h-10 w-full" />
        </div>
      );
    }

    if (formattedProxies.length === 0) {
      return (
        <Card className="col-span-full">
          <CardHeader>
            <CardTitle className="flex items-center">
              <Info className="mr-2 h-6 w-6 text-blue-500" />
              No Active Proxies Found
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">
              There are currently no proxies in a 'running' state.
            </p>
            <p className="text-muted-foreground mt-2">
              To see proxies here, please ensure:
            </p>
            <ul className="list-disc list-inside text-muted-foreground mt-1 space-y-1">
              <li>A modem is 'connected' on the "Modem Status" page.</li>
              <li>The proxy server has been started and is 'running' on the "Proxy Control" page.</li>
            </ul>
          </CardContent>
        </Card>
      );
    }

    return (
      <>
        {/* Table view for Desktop */}
        <div className="hidden md:block rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Proxy Name</TableHead>
                <TableHead>IP Address</TableHead>
                <TableHead>Port</TableHead>
                <TableHead>Username</TableHead>
                <TableHead>Password</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {formattedProxies.map((proxy) => (
                <TableRow key={proxy.id}>
                  <TableCell>
                    <div className="font-medium">{proxy.name}</div>
                    <div className="text-xs text-muted-foreground">{proxy.interfaceName}</div>
                  </TableCell>
                  <TableCell className="font-mono text-sm">{proxy.ipAddress}</TableCell>
                   <TableCell className="font-mono text-sm">{proxy.port}</TableCell>
                   <TableCell className="font-mono text-sm">{proxy.username || 'N/A'}</TableCell>
                   <TableCell className="font-mono text-sm">{proxy.password ? '••••••' : 'N/A'}</TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0">
                          <ClipboardCopy className="h-4 w-4" />
                          <span className="sr-only">Copy options</span>
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => handleCopyToClipboard(proxy.proxyString, "Full String", proxy.name)}>
                          <Copy className="mr-2 h-4 w-4" /> Copy Full String
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleCopyToClipboard(proxy.ipAddress, "IP Address", proxy.name)}>
                          <NetworkIcon className="mr-2 h-4 w-4" /> Copy IP
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleCopyToClipboard(proxy.port, "Port", proxy.name)}>
                           <Binary className="mr-2 h-4 w-4" /> Copy Port
                        </DropdownMenuItem>
                         {proxy.username && <DropdownMenuItem onClick={() => handleCopyToClipboard(proxy.username, "Username", proxy.name)}>
                           <User className="mr-2 h-4 w-4" /> Copy Username
                        </DropdownMenuItem>}
                        {proxy.password && <DropdownMenuItem onClick={() => handleCopyToClipboard(proxy.password, "Password", proxy.name)}>
                           <Lock className="mr-2 h-4 w-4" /> Copy Password
                        </DropdownMenuItem>}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        {/* Card view for Mobile */}
        <div className="grid gap-6 md:hidden">
          {formattedProxies.map((proxy) => (
            <Card key={proxy.id} className="shadow-md">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg flex items-center gap-2">{proxy.name}
                     <Badge variant={proxy.username ? 'default' : 'secondary'}
                        className={`
                        ${proxy.username ? 'bg-blue-500/20 text-blue-700 border-blue-500' : 'bg-yellow-500/20 text-yellow-700 border-yellow-500'}
                        `}
                    >
                        {proxy.username ? <Lock className="inline mr-1 h-3 w-3" /> : <KeyRound className="inline mr-1 h-3 w-3" />}
                        {proxy.username ? 'Authenticated' : 'Open'}
                    </Badge>
                  </CardTitle>
                </div>
                <CardDescription>Interface: {proxy.interfaceName}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between p-2 bg-muted rounded-md text-sm font-mono">
                  <code className="truncate" title={proxy.proxyString}>{proxy.proxyString}</code>
                  <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => handleCopyToClipboard(proxy.proxyString, "Full String", proxy.name)}>
                    <ClipboardCopy className="h-4 w-4" />
                    <span className="sr-only">Copy full string</span>
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Format: IP:Port{proxy.username && ':User:Pass'}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </>
    );
  };

  return (
    <>
      <PageHeader
        title="Active Proxy List"
        description="List of all currently active proxies, both authenticated and open."
        actions={
          <Button onClick={fetchAndFormatProxies} disabled={isLoading} variant="outline">
            <ListChecks className="mr-2 h-4 w-4" />
            Refresh List
          </Button>
        }
      />
      
      {renderContent()}
    </>
  );
}
