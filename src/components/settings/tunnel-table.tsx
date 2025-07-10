
'use client';

import { useState, useEffect, useCallback } from 'react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { RefreshCw, Loader2, Info, Waypoints } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { getAllTunnelStatuses, TunnelStatus } from '@/services/tunnel-service';
import { Skeleton } from '@/components/ui/skeleton';

export function TunnelTable() {
  const [tunnels, setTunnels] = useState<TunnelStatus[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const { toast } = useToast();

  const fetchTunnels = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await getAllTunnelStatuses();
      setTunnels(data);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Failed to fetch tunnel statuses.";
      toast({ title: "Error", description: errorMessage, variant: "destructive" });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchTunnels();
  }, [fetchTunnels]);

  const renderStatusBadge = (status: TunnelStatus['status']) => {
    switch (status) {
      case 'active':
        return <Badge className="bg-green-500/20 text-green-700 border-green-500">Active</Badge>;
      case 'inactive':
        return <Badge variant="secondary">Inactive</Badge>;
      case 'error':
        return <Badge variant="destructive">Error</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  return (
    <div>
      <div className="flex justify-end mb-4">
        <Button onClick={fetchTunnels} disabled={isLoading} variant="outline" size="sm">
          <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh List
        </Button>
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Tunnel ID</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Public URL</TableHead>
              <TableHead>Linked To</TableHead>
              <TableHead className="text-right">Local Port</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              [...Array(3)].map((_, i) => (
                <TableRow key={i}>
                  <TableCell><Skeleton className="h-5 w-24" /></TableCell>
                  <TableCell><Skeleton className="h-5 w-16" /></TableCell>
                  <TableCell><Skeleton className="h-6 w-20 rounded-full" /></TableCell>
                  <TableCell><Skeleton className="h-5 w-48" /></TableCell>
                   <TableCell><Skeleton className="h-5 w-20" /></TableCell>
                  <TableCell className="text-right"><Skeleton className="h-5 w-12 ml-auto" /></TableCell>
                </TableRow>
              ))
            ) : tunnels.length > 0 ? (
              tunnels.map((tunnel) => (
                <TableRow key={tunnel.id}>
                  <TableCell className="font-mono text-xs">{tunnel.id}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="flex items-center gap-1 w-fit">
                        <Waypoints className="h-3 w-3" />
                        {tunnel.type}
                    </Badge>
                  </TableCell>
                  <TableCell>{renderStatusBadge(tunnel.status)}</TableCell>
                  <TableCell className="font-mono text-xs">{tunnel.url || 'N/A'}</TableCell>
                  <TableCell>{tunnel.linkedTo || 'N/A'}</TableCell>
                  <TableCell className="text-right">{tunnel.localPort}</TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={6} className="h-24 text-center">
                  <Info className="mx-auto h-6 w-6 text-muted-foreground mb-2" />
                  No active tunnels found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
