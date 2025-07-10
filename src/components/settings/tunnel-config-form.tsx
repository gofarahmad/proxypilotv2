
'use client';

import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { useToast } from '@/hooks/use-toast';
import { getAllModemStatuses, ModemStatus } from '@/services/network-service';
import { startTunnel, getAvailableCloudflareTunnels, CloudflareTunnel } from '@/services/tunnel-service';
import { getProxyConfig } from '@/services/proxy-service';
import { Loader2, PlugZap, Cloud, Power } from 'lucide-react';

const TunnelConfigSchema = z.object({
  tunnelType: z.enum(['Ngrok', 'Cloudflare']),
  // Depending on tunnelType, one of the following will be required.
  // We use .optional() here and validate in the onSubmit handler.
  ngrokTargetInterface: z.string().optional(),
  cloudflareTunnelId: z.string().optional(),
  cloudflareTargetInterface: z.string().optional(),
});

type TunnelConfigValues = z.infer<typeof TunnelConfigSchema>;

export function TunnelConfigForm() {
  const { toast } = useToast();
  const [eligibleModems, setEligibleModems] = useState<ModemStatus[]>([]);
  const [cloudflareTunnels, setCloudflareTunnels] = useState<CloudflareTunnel[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  
  const form = useForm<TunnelConfigValues>({
    resolver: zodResolver(TunnelConfigSchema),
    defaultValues: {
      tunnelType: 'Ngrok',
    },
  });

  const tunnelType = form.watch('tunnelType');

  useEffect(() => {
    async function fetchData() {
      try {
        const modemStatuses = await getAllModemStatuses();
        const runningModems = modemStatuses.filter(m => m.status === 'connected' && m.proxyStatus === 'running');
        setEligibleModems(runningModems);
        
        const cfTunnels = await getAvailableCloudflareTunnels();
        setCloudflareTunnels(cfTunnels);
      } catch (error) {
        toast({
          title: "Error fetching initial data",
          description: error instanceof Error ? error.message : "Could not load modem or tunnel list.",
          variant: "destructive",
        });
      }
    }
    fetchData();
  }, [toast]);

  async function onSubmit(data: TunnelConfigValues) {
    setIsLoading(true);
    try {
      let tunnelId: string;
      let localPort: number;
      let linkedTo: string;
      let cloudflareId: string | undefined;

      if (data.tunnelType === 'Ngrok') {
        if (!data.ngrokTargetInterface) throw new Error("Please select a modem for the Ngrok tunnel.");
        
        const selectedModem = eligibleModems.find(m => m.interfaceName === data.ngrokTargetInterface);
        if (!selectedModem) throw new Error("Selected modem not found or is no longer eligible.");
        
        const proxyConfig = await getProxyConfig(data.ngrokTargetInterface);
        if (!proxyConfig?.port) throw new Error(`Proxy port for ${data.ngrokTargetInterface} is not configured.`);
        
        tunnelId = `tunnel_${data.ngrokTargetInterface}`;
        localPort = proxyConfig.port;
        linkedTo = selectedModem.name;

      } else if (data.tunnelType === 'Cloudflare') {
        if (!data.cloudflareTunnelId) throw new Error("Please select a pre-configured Cloudflare tunnel.");
        if (!data.cloudflareTargetInterface) throw new Error("Please select a local proxy to connect to.");

        const selectedModem = eligibleModems.find(m => m.interfaceName === data.cloudflareTargetInterface);
        if (!selectedModem) throw new Error("Selected target modem not found or is no longer eligible.");
        
        const proxyConfig = await getProxyConfig(data.cloudflareTargetInterface);
        if (!proxyConfig?.port) throw new Error(`Proxy port for ${data.cloudflareTargetInterface} is not configured.`);

        tunnelId = `tunnel_cf_${data.cloudflareTunnelId}`; // Use a unique ID format for CF tunnels
        localPort = proxyConfig.port;
        linkedTo = `CF: ${data.cloudflareTunnelId.substring(0, 8)}... -> ${selectedModem.name}`;
        cloudflareId = data.cloudflareTunnelId;
      
      } else {
        throw new Error("Invalid tunnel type selected.");
      }

      await startTunnel(tunnelId, localPort, linkedTo, data.tunnelType, cloudflareId);

      toast({
          title: "Tunnel Creation Initiated",
          description: `A ${data.tunnelType} tunnel is being created. Check the Active Tunnels table for status.`,
      });
      
      setTimeout(() => {
          window.dispatchEvent(new CustomEvent('refreshTunnels'));
      }, 2500);

    } catch (error) {
      toast({
        title: "Tunnel Creation Failed",
        description: error instanceof Error ? error.message : "An unknown error occurred.",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <FormField
          control={form.control}
          name="tunnelType"
          render={({ field }) => (
              <FormItem>
              <FormLabel>Tunnel Provider</FormLabel>
              <Select onValueChange={(value) => {
                  field.onChange(value);
                  form.reset({
                      ...form.getValues(),
                      tunnelType: value as 'Ngrok' | 'Cloudflare',
                      ngrokTargetInterface: '',
                      cloudflareTunnelId: '',
                      cloudflareTargetInterface: '',
                  });
              }} defaultValue={field.value}>
                  <FormControl>
                  <SelectTrigger>
                      <SelectValue placeholder="Select a provider" />
                  </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                      <SelectItem value="Ngrok"><Power className="inline-flex mr-2 h-4 w-4"/>Ngrok (Ephemeral)</SelectItem>
                      <SelectItem value="Cloudflare"><Cloud className="inline-flex mr-2 h-4 w-4"/>Cloudflare (Permanent)</SelectItem>
                  </SelectContent>
              </Select>
              <FormMessage />
              </FormItem>
          )}
        />
        
        {tunnelType === 'Ngrok' && (
             <FormField
                control={form.control}
                name="ngrokTargetInterface"
                render={({ field }) => (
                    <FormItem>
                        <FormLabel>Target Running Proxy</FormLabel>
                        <Select onValueChange={field.onChange} defaultValue={field.value}>
                            <FormControl>
                                <SelectTrigger>
                                    <SelectValue placeholder="Choose a modem with a running proxy..." />
                                </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                            {eligibleModems.length > 0 ? eligibleModems.map(modem => (
                                <SelectItem key={modem.interfaceName} value={modem.interfaceName}>
                                {modem.name} ({modem.interfaceName}) - IP: {modem.ipAddress}
                                </SelectItem>
                            )) : (
                                <SelectItem value="none" disabled>No eligible modems found</SelectItem>
                            )}
                            </SelectContent>
                        </Select>
                        <FormMessage />
                    </FormItem>
                )}
            />
        )}

        {tunnelType === 'Cloudflare' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <FormField
                    control={form.control}
                    name="cloudflareTunnelId"
                    render={({ field }) => (
                        <FormItem>
                            <FormLabel>Available Cloudflare Tunnels</FormLabel>
                            <Select onValueChange={field.onChange} defaultValue={field.value}>
                                <FormControl>
                                <SelectTrigger>
                                    <SelectValue placeholder="Select a pre-configured tunnel..." />
                                </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                {cloudflareTunnels.length > 0 ? cloudflareTunnels.map(tunnel => (
                                    <SelectItem key={tunnel.id} value={tunnel.id}>
                                    {tunnel.name}
                                    </SelectItem>
                                )) : (
                                    <SelectItem value="none" disabled>No Cloudflare tunnels detected</SelectItem>
                                )}
                                </SelectContent>
                            </Select>
                            <FormMessage />
                        </FormItem>
                    )}
                />
                <FormField
                    control={form.control}
                    name="cloudflareTargetInterface"
                    render={({ field }) => (
                        <FormItem>
                            <FormLabel>Target Local Proxy</FormLabel>
                            <Select onValueChange={field.onChange} defaultValue={field.value}>
                                <FormControl>
                                <SelectTrigger>
                                    <SelectValue placeholder="Link to running proxy..." />
                                </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                {eligibleModems.length > 0 ? eligibleModems.map(modem => (
                                    <SelectItem key={modem.interfaceName} value={modem.interfaceName}>
                                    {modem.name} (Port: {modem.ipAddress})
                                    </SelectItem>
                                )) : (
                                    <SelectItem value="none" disabled>No eligible proxies found</SelectItem>
                                )}
                                </SelectContent>
                            </Select>
                            <FormMessage />
                        </FormItem>
                    )}
                />
            </div>
        )}

        <Button type="submit" disabled={isLoading || eligibleModems.length === 0}>
            {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PlugZap className="mr-2 h-4 w-4" />}
            Create Tunnel
        </Button>
      </form>
    </Form>
  );
}

    