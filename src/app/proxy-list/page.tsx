
'use client';

import { useEffect, useState, useCallback } from 'react';
import { PageHeader } from '@/components/page-header';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Signal, SignalHigh, SignalLow, SignalMedium, Copy, HardDrive, Wifi, KeyRound, User, Link as LinkIcon, Server, Globe, RefreshCw, Loader2, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { useIsMobile } from '@/hooks/use-is-mobile';
import { Separator } from '@/components/ui/separator';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Skeleton } from '@/components/ui/skeleton';
import { getAllModemStatuses, ModemStatus as BackendModemStatus } from '@/services/network-service';


type ProxyConfig = {
  type: 'http' | 'socks';
  port: number;
  username: string;
  pass: string;
};

type Modem = {
  id: string;
  name: string;
  ip: string;
  status: 'active' | 'inactive' | 'failed';
  provider: string;
  signal: number; // 0-3 for no signal, low, medium, high
  proxies: ProxyConfig[];
};

// --- Helper Functions ---

const transformBackendDataToFrontend = (backendModems: BackendModemStatus[]): Modem[] => {
  return backendModems
    .filter(bm => bm.status === 'connected' && bm.proxyStatus === 'running' && bm.proxyConfig && bm.ipAddress)
    .map(bm => {
      
      const getSignalLevel = (rssiStr: string | undefined): number => {
          if (!rssiStr) return 0;
          const rssi = parseInt(rssiStr.replace(' dBm', ''), 10);
          if (isNaN(rssi)) return 0;

          if (rssi >= -70) return 3; // High
          if (rssi >= -85) return 2; // Medium
          if (rssi >= -100) return 1; // Low
          return 0; // No signal / very poor
      };
      
      const getStatus = (backendStatus: BackendModemStatus['status'], proxyStatus: BackendModemStatus['proxyStatus']): Modem['status'] => {
          if (backendStatus === 'connected' && proxyStatus === 'running') return 'active';
          if (backendStatus === 'error' || proxyStatus === 'error') return 'failed';
          return 'inactive';
      };

      const proxyConfig = bm.proxyConfig!;
      const httpProxy: ProxyConfig | null = proxyConfig.httpPort ? {
          type: 'http',
          port: proxyConfig.httpPort,
          username: proxyConfig.username || '',
          pass: proxyConfig.password || ''
      } : null;
      
      return {
        id: bm.id,
        name: bm.name,
        ip: bm.serverLanIp || '127.0.0.1', // Fallback to serverLanIp or localhost
        status: getStatus(bm.status, bm.proxyStatus),
        provider: bm.details?.operator || 'Unknown',
        signal: getSignalLevel(bm.details?.rssi),
        proxies: httpProxy ? [httpProxy] : [], // Only including HTTP proxy for now
      };
    })
    .filter(m => m.proxies.length > 0);
};


const getStatusBadge = (status: Modem['status']) => {
    switch (status) {
      case 'active':
        return <Badge variant="default" className="bg-green-600 hover:bg-green-700">Active</Badge>;
      case 'inactive':
        return <Badge variant="secondary">Inactive</Badge>;
      case 'failed':
        return <Badge variant="destructive">Failed</Badge>;
    }
  };

const SignalStrength = ({ level }: { level: number }) => {
  if (level >= 3) return <SignalHigh className="text-green-500" />;
  if (level === 2) return <SignalMedium className="text-yellow-500" />;
  if (level === 1) return <SignalLow className="text-orange-500" />;
  return <Signal className="text-red-500" />;
};

const CopyableField = ({ value, label, tooltip, icon: Icon, isSecret = false }: { value: string | number; label: string; tooltip: string, icon: React.ElementType, isSecret?: boolean }) => {
    const { toast } = useToast();

    const handleCopy = (e: React.MouseEvent) => {
        e.stopPropagation();
        navigator.clipboard.writeText(String(value));
        toast({
            title: 'Copied to Clipboard',
            description: `${label} has been copied.`,
        });
    };

    return (
        <div className="flex-1 min-w-0">
            <Label className="text-xs text-muted-foreground flex items-center gap-1.5 mb-1">
                <Icon className="h-3 w-3" />
                {label}
            </Label>
            <div className="relative flex items-center">
                 <Input 
                    type={isSecret ? "password" : "text"} 
                    readOnly 
                    value={String(value)} 
                    className="h-8 flex-grow bg-muted border-none focus-visible:ring-0 focus-visible:ring-offset-0 pr-8"
                 />
                 <TooltipProvider>
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button variant="ghost" size="icon" className="absolute right-0 top-0 h-8 w-8 shrink-0" onClick={handleCopy}>
                                <Copy className="h-4 w-4" />
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent>
                            <p>{tooltip}</p>
                        </TooltipContent>
                    </Tooltip>
                </TooltipProvider>
            </div>
        </div>
    );
};


const CopyAddress = ({ ip, port, username, pass }: { ip: string; port: number, username: string, pass: string }) => {
  const { toast } = useToast();
  const address = `${ip}:${port}:${username}:${pass}`;

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(address);
    toast({
      title: 'Copied',
      description: `Proxy connection string copied to clipboard.`,
    });
  };

  return (
     <TooltipProvider>
        <Tooltip>
            <TooltipTrigger asChild>
                 <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleCopy}>
                    <LinkIcon className="h-4 w-4" />
                </Button>
            </TooltipTrigger>
            <TooltipContent align="end">
                <p className="font-mono text-xs">{address}</p>
                 <p className="text-xs text-muted-foreground">Copy Connection String</p>
            </TooltipContent>
        </Tooltip>
    </TooltipProvider>
  );
};


// --- Views ---

const DesktopView = ({ modems }: { modems: Modem[] }) => (
  <Card>
    <CardHeader>
      <CardTitle>Proxy Status</CardTitle>
      <CardDescription>Detailed overview of your active proxies.</CardDescription>
    </CardHeader>
    <CardContent>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[100px]">Status</TableHead>
            <TableHead>Modem</TableHead>
            <TableHead>Provider</TableHead>
            <TableHead>Proxies</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {modems.map((modem) => (
            <TableRow key={modem.id}>
              <TableCell>{getStatusBadge(modem.status)}</TableCell>
              <TableCell>
                <div className="font-medium">{modem.name}</div>
                <div className="text-sm text-muted-foreground">{modem.ip}</div>
              </TableCell>
              <TableCell>{modem.provider}</TableCell>
              <TableCell>
                <div className="flex flex-col gap-4">
                    {modem.proxies.map((proxy, index) => (
                        <div key={proxy.port} className="flex flex-col gap-2">
                             {index > 0 && <Separator className="my-2"/>}
                             <div className="flex items-center gap-2">
                                <SignalStrength level={modem.signal} />
                                <CopyAddress ip={modem.ip} port={proxy.port} username={proxy.username} pass={proxy.pass}/>
                             </div>
                             <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                                <CopyableField value={modem.ip} label="IP Address" tooltip="Copy IP Address" icon={Globe} />
                                <CopyableField value={proxy.port} label="Port" tooltip="Copy Port" icon={Server} />
                                <CopyableField value={proxy.username} label="Username" tooltip="Copy Username" icon={User} />
                                <CopyableField value={proxy.pass} label="Password" tooltip="Copy Password" icon={KeyRound} isSecret={true}/>
                             </div>
                        </div>
                    ))}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </CardContent>
  </Card>
);

const MobileView = ({ modems }: { modems: Modem[] }) => (
    <div className="space-y-4">
        {modems.map((modem) => (
            <Card key={modem.id}>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <CardTitle className="flex items-center gap-2">
                             <HardDrive className="h-5 w-5 text-primary"/> {modem.name}
                        </CardTitle>
                        {getStatusBadge(modem.status)}
                    </div>
                     <CardDescription className="flex items-center gap-2 pt-1">
                        <Wifi className="h-4 w-4"/> {modem.provider}
                     </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {modem.proxies.map((proxy, index) => (
                        <div key={proxy.port}>
                             {index > 0 && <Separator className="my-4"/>}
                             <div className="space-y-3">
                                 <div className="flex items-center gap-2">
                                    <SignalStrength level={modem.signal}/>
                                    <CopyAddress ip={modem.ip} port={proxy.port} username={proxy.username} pass={proxy.pass}/>
                                 </div>
                                <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                                     <CopyableField value={modem.ip} label="IP Address" tooltip="Copy IP Address" icon={Globe} />
                                     <CopyableField value={proxy.port} label="Port" tooltip="Copy Port" icon={Server} />
                                     <CopyableField value={proxy.username} label="Username" tooltip="Copy Username" icon={User} />
                                     <CopyableField value={proxy.pass} label="Password" tooltip="Copy Password" icon={KeyRound} isSecret={true}/>
                                </div>
                             </div>
                        </div>
                    ))}
                </CardContent>
            </Card>
        ))}
    </div>
);

// --- Main Page Component ---

export default function ProxyListPage() {
  const [modems, setModems] = useState<Modem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const { toast } = useToast();
  const isMobile = useIsMobile();

  const fetchProxies = useCallback(async () => {
    setIsLoading(true);
    try {
      const backendData = await getAllModemStatuses();
      const formattedData = transformBackendDataToFrontend(backendData);
      setModems(formattedData);
    } catch (error) {
      toast({
        title: "Error",
        description: `Could not fetch proxy list: ${error instanceof Error ? error.message : 'Unknown error'}`,
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchProxies();
  }, [fetchProxies]);

  const renderContent = () => {
    if (isLoading) {
       return isMobile 
        ? <Skeleton className="h-64 w-full" />
        : <Skeleton className="h-64 w-full" />;
    }

    if (modems.length === 0) {
      return (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Info className="h-5 w-5 text-primary"/>No Active Proxies</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">No active and running proxies were found.</p>
             <p className="text-muted-foreground mt-2">
              Please ensure your modems are connected, have a signal, and their proxies have been started on the "Proxy Control" page.
            </p>
          </CardContent>
        </Card>
      )
    }

    return isMobile ? <MobileView modems={modems} /> : <DesktopView modems={modems} />;
  };

  return (
     <>
      <PageHeader
        title="Active Proxy List"
        description="Overview of all currently active and usable proxies."
        actions={
          <Button onClick={fetchProxies} disabled={isLoading} variant="outline">
            <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        }
      />
      {renderContent()}
    </>
  );
}
