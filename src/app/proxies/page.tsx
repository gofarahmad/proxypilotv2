
'use client';

import { PageHeader } from '@/components/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Network, Play, StopCircle, RefreshCw, Loader2, ServerCrash, ShieldQuestion, Waypoints, AlertTriangle, KeyRound, Lock, Pencil } from 'lucide-react';
import { useState, useEffect, useCallback, useRef } from 'react';
import { useToast } from '@/hooks/use-toast';
import { Skeleton } from '@/components/ui/skeleton';
import type { ModemStatus } from '@/services/network-service';
import { getAllModemStatuses } from '@/services/network-service';
import { startProxy, stopProxy, restartProxy, getProxyConfig, updateProxyCredentials, ProxyConfig } from '@/services/proxy-service';
import { startTunnel, stopTunnel, getTunnelStatus, TunnelStatus } from '@/services/tunnel-service';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
  DialogClose
} from "@/components/ui/dialog";
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface ProxyInstance extends ModemStatus {
  proxyLoading: boolean;
  tunnelLoading: boolean;
  config: ProxyConfig | null;
  tunnel?: TunnelStatus | null;
}

function CredentialsDialog({ proxy, onCredentialsUpdate }: { proxy: ProxyInstance; onCredentialsUpdate: () => void }) {
  const [username, setUsername] = useState(proxy.config?.username || '');
  const [password, setPassword] = useState(proxy.config?.password || '');
  const [isLoading, setIsLoading] = useState(false);
  const { toast } = useToast();

  const handleSave = async () => {
    setIsLoading(true);
    try {
      await updateProxyCredentials(proxy.interfaceName, username, password);
      toast({
        title: "Credentials Updated",
        description: `Credentials for ${proxy.name} have been saved. Proxy is restarting.`,
      });
      onCredentialsUpdate();
    } catch (error) {
      toast({
        title: "Update Failed",
        description: error instanceof Error ? error.message : "Could not update credentials.",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="h-7 text-xs">
            <Pencil className="mr-2 h-3 w-3" />
            Edit
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Credentials for {proxy.name}</DialogTitle>
          <DialogDescription>
            Set or update the username and password for this proxy. Leave both fields blank to run an open, unauthenticated proxy. The proxy will restart automatically on save.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="username" className="text-right">Username</Label>
            <Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} className="col-span-3" />
          </div>
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="password" className="text-right">Password</Label>
            <Input id="password" value={password} onChange={(e) => setPassword(e.target.value)} className="col-span-3" />
          </div>
        </div>
        <DialogFooter>
            <DialogClose asChild>
                <Button type="button" variant="secondary">Cancel</Button>
            </DialogClose>
            <DialogClose asChild>
                <Button onClick={handleSave} disabled={isLoading}>
                    {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Save & Restart Proxy
                </Button>
            </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function ProxyControlPage() {
  const [proxies, setProxies] = useState<ProxyInstance[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();
  const activePolls = useRef(new Set<string>()).current;

  const fetchProxiesData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
        setIsLoading(true);
    }
    setError(null);
    try {
      const modemData = await getAllModemStatuses();
      
      const proxiesWithDetails = await Promise.all(
        modemData.map(async (m) => {
          const existingProxy = proxies.find(p => p.interfaceName === m.interfaceName);

          return { 
            ...m, 
            proxyLoading: existingProxy?.proxyLoading || false, 
            tunnelLoading: existingProxy?.tunnelLoading || false,
            config: m.proxyConfig || null,
            tunnel: null // Tunnel data will be loaded from settings page now
          };
        })
      );
      
      setProxies(proxiesWithDetails);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "An unknown error occurred";
      toast({ title: 'Error fetching proxies', description: errorMessage, variant: 'destructive' });
      setError("Could not load proxy data. Please ensure the backend service is running correctly.");
    } finally {
      if (isRefresh) {
        setIsLoading(false);
      }
    }
  }, [toast, proxies]);

  useEffect(() => {
    setIsLoading(true);
    fetchProxiesData(false).finally(() => setIsLoading(false));
    const interval = setInterval(() => fetchProxiesData(false), 30000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pollForStatusChange = useCallback(async (interfaceName: string, targetStatus: 'running' | 'stopped') => {
      if (activePolls.has(interfaceName)) return;
      activePolls.add(interfaceName);

      let attempts = 0;
      const maxAttempts = 5; // Poll for 10 seconds (5 attempts * 2s delay)

      const poll = async () => {
          if (attempts >= maxAttempts) {
              setProxies(prev => prev.map(p => p.interfaceName === interfaceName ? { ...p, proxyLoading: false } : p));
              activePolls.delete(interfaceName);
              return;
          }

          attempts++;
          const allStatuses = await getAllModemStatuses();
          const currentProxy = allStatuses.find(m => m.interfaceName === interfaceName);

          if (currentProxy?.proxyStatus === targetStatus) {
              setProxies(prev => allStatuses.map(newStatus => ({
                  ...newStatus,
                  proxyLoading: false,
                  tunnelLoading: prev.find(p => p.interfaceName === newStatus.interfaceName)?.tunnelLoading || false,
                  config: newStatus.proxyConfig || null,
                  tunnel: null, // This will be repopulated on next full fetch
              })));
              activePolls.delete(interfaceName);
              fetchProxiesData(false); // Do a final full fetch
          } else {
              setTimeout(poll, 2000);
          }
      };

      poll();
  }, [activePolls, fetchProxiesData]);

  const handleProxyAction = async (interfaceName: string, action: 'start' | 'stop' | 'restart') => {
    setProxies(prev => prev.map(p => p.interfaceName === interfaceName ? { ...p, proxyLoading: true } : p));
    
    try {
      const targetStatus = (action === 'start' || action === 'restart') ? 'running' : 'stopped';

      if (action === 'start') await startProxy(interfaceName);
      else if (action === 'stop') await stopProxy(interfaceName);
      else await restartProxy(interfaceName);

      toast({
        title: `Proxy ${action} initiated`,
        description: `Request to ${action} proxy on ${interfaceName} sent.`,
      });

      await pollForStatusChange(interfaceName, targetStatus);

    } catch (error) {
       const errorMessage = error instanceof Error ? error.message : "An unknown error occurred";
      toast({ title: `Error ${action}ing proxy`, description: errorMessage, variant: 'destructive' });
      setProxies(prev => prev.map(p => p.interfaceName === interfaceName ? { ...p, proxyLoading: false } : p));
    }
  };

  const renderContent = () => {
    if (isLoading) {
      return (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-[320px] w-full rounded-lg" />)}
        </div>
      );
    }

    if(error) {
       return (
         <div className="text-center py-10 bg-destructive/10 border border-destructive/20 rounded-lg">
            <AlertTriangle className="mx-auto h-12 w-12 text-destructive mb-4" />
            <p className="text-xl text-destructive/90 font-semibold">Could not load proxies</p>
            <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">{error}</p>
          </div>
       );
    }
    
    if (proxies.length === 0) {
      return (
         <div className="text-center py-10">
            <ShieldQuestion className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-xl text-muted-foreground">No modems found.</p>
            <p className="text-sm text-muted-foreground mt-2">Connect a USB modem to see proxy controls here.</p>
          </div>
      );
    }

    return (
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {proxies.map((proxy) => {
          const isAuthenticated = proxy.config?.username && proxy.config?.password;
          const httpPort = proxy.config?.httpPort || 'N/A';
          const socksPort = proxy.config?.socksPort || 'N/A';

          return (
            <Card key={proxy.interfaceName} className={`shadow-md flex flex-col ${proxy.status !== 'connected' ? 'bg-muted/30' : ''}`}>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <CardTitle className="text-lg">Proxy on {proxy.name}</CardTitle>
                        <Network className="h-5 w-5 text-primary" />
                    </div>
                    <CardDescription>
                      IF: {proxy.interfaceName} | IP: {proxy.ipAddress || 'N/A'}
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 flex-grow flex flex-col justify-between">
                <div>
                    <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">HTTP Port:</span>
                        <span className="font-mono text-sm">{httpPort}</span>
                    </div>
                    <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">SOCKS5 Port:</span>
                        <span className="font-mono text-sm">{socksPort}</span>
                    </div>

                    <div className="flex items-center justify-between mt-2">
                        <span className="text-sm font-medium">Proxy Status:</span>
                        <Badge variant={proxy.proxyStatus === 'running' ? 'default' : (proxy.proxyStatus === 'stopped' ? 'secondary' : 'destructive')}
                            className={`
                            ${proxy.proxyStatus === 'running' ? 'bg-green-500/20 text-green-700 border-green-500' : ''}
                            ${proxy.proxyStatus === 'stopped' ? 'bg-gray-500/20 text-gray-700 border-gray-500' : ''}
                            ${proxy.proxyStatus === 'error' ? 'bg-red-500/20 text-red-700 border-red-500' : ''}
                            `}
                        >
                            {proxy.proxyStatus === 'error' ? <ServerCrash className="inline mr-1 h-4 w-4" /> : null}
                            {proxy.proxyStatus}
                        </Badge>
                    </div>

                    <div className="flex items-center justify-between mt-2">
                        <span className="text-sm font-medium">Authentication:</span>
                        <div className="flex items-center gap-2">
                            <Badge variant={isAuthenticated ? 'default' : 'secondary'}
                                className={`
                                ${isAuthenticated ? 'bg-blue-500/20 text-blue-700 border-blue-500' : 'bg-yellow-500/20 text-yellow-700 border-yellow-500'}
                                `}
                            >
                                {isAuthenticated ? <Lock className="inline mr-1 h-3 w-3" /> : <KeyRound className="inline mr-1 h-3 w-3" />}
                                {isAuthenticated ? 'Authenticated' : 'Open (No Auth)'}
                            </Badge>
                            <CredentialsDialog proxy={proxy} onCredentialsUpdate={() => fetchProxiesData(true)} />
                        </div>
                    </div>
                </div>
                
                <div className="space-y-2 pt-4">
                    <div className="grid grid-cols-3 gap-2">
                    <Button 
                        onClick={() => handleProxyAction(proxy.interfaceName, 'start')} 
                        disabled={proxy.proxyLoading || proxy.proxyStatus === 'running' || proxy.status !== 'connected'}
                        size="sm" variant="ghost" className="text-green-600 hover:text-green-700 hover:bg-green-100"
                        title={proxy.status !== 'connected' ? 'Modem not connected' : 'Start Proxy'}
                    >
                        {proxy.proxyLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Start
                    </Button>
                    <Button 
                        onClick={() => handleProxyAction(proxy.interfaceName, 'stop')} 
                        disabled={proxy.proxyLoading || proxy.proxyStatus !== 'running'}
                        size="sm" variant="ghost" className="text-red-600 hover:text-red-700 hover:bg-red-100"
                        title={proxy.proxyStatus !== 'running' ? 'Proxy not running' : 'Stop Proxy'}
                    >
                        {proxy.proxyLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <StopCircle className="h-4 w-4" />} Stop
                    </Button>
                    <Button 
                        onClick={() => handleProxyAction(proxy.interfaceName, 'restart')} 
                        disabled={proxy.proxyLoading || proxy.status !== 'connected'}
                        size="sm" variant="ghost" className="text-blue-600 hover:text-blue-700 hover:bg-blue-100"
                        title={proxy.status !== 'connected' ? 'Modem not connected' : 'Restart Proxy'}
                    >
                    {proxy.proxyLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Restart
                    </Button>
                    </div>
                </div>
                </CardContent>
            </Card>
          )
        })}
      </div>
    )
  }

  return (
    <>
      <PageHeader
        title="Proxy Control"
        description="Start, stop, and manage credentials for your proxy servers."
        actions={
          <Button onClick={() => fetchProxiesData(true)} disabled={isLoading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh All
          </Button>
        }
      />
      {renderContent()}
    </>
  );
}

    