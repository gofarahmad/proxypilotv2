
'use client';

import { PageHeader } from '@/components/page-header';
import { ModemStatusCard } from '@/components/dashboard/modem-status-card';
import { getAllModemStatuses, ModemStatus as ModemStatusType, updateProxyConfig } from '@/services/network-service';
import { useEffect, useState, useCallback, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { RefreshCw, Wifi, AlertTriangle, Loader2 } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { useToast } from '@/hooks/use-toast';

export default function ModemStatusPage() {
  const [modems, setModems] = useState<ModemStatusType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showTimeoutMessage, setShowTimeoutMessage] = useState(false);
  const { toast } = useToast();
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  const fetchModems = useCallback(async (isRefresh = false) => {
    setIsLoading(true);
    setError(null);
    setShowTimeoutMessage(false);
    if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
    }
    
    if(isRefresh) {
        toast({ title: "Refreshing...", description: "Fetching latest modem statuses." });
    }

    timeoutRef.current = setTimeout(() => {
        if (isLoading) {
            setShowTimeoutMessage(true);
        }
    }, 10000); 

    try {
      const data = await getAllModemStatuses();
      setModems(data);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "An unknown error occurred";
      console.error("Failed to fetch modem statuses:", errorMessage);
      setError(errorMessage);
      setModems([]); 
      toast({ title: "Error Fetching Modems", description: errorMessage, variant: "destructive" });
    } finally {
      setIsLoading(false);
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    }
  }, [toast, isLoading]);


  useEffect(() => {
    fetchModems(false);
    return () => {
        if(timeoutRef.current) clearTimeout(timeoutRef.current);
    }
  }, []);

  const handleNameUpdate = async (interfaceName: string, newName: string) => {
    const originalModems = [...modems];
    
    // Optimistic UI update
    setModems(prevModems =>
      prevModems.map(m => (m.interfaceName === interfaceName ? { ...m, name: newName } : m))
    );

    try {
      await updateProxyConfig(interfaceName, { customName: newName });
      toast({
        title: "Name Updated",
        description: `Modem ${interfaceName} is now named "${newName}".`,
      });
    } catch (error) {
      // Revert on error
      setModems(originalModems);
      const errorMessage = error instanceof Error ? error.message : "An unknown error occurred";
      toast({
        title: "Update Failed",
        description: errorMessage,
        variant: "destructive",
      });
    }
  };

  const renderContent = () => {
    if (isLoading && modems.length === 0 && !error) {
      return (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-[420px] w-full rounded-lg" />)}
          {showTimeoutMessage && (
              <div className="md:col-span-2 lg:col-span-3 text-center py-10 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                <Loader2 className="mx-auto h-12 w-12 text-blue-500 mb-4 animate-spin" />
                <p className="text-xl text-blue-500/90 font-semibold">Still searching for modems...</p>
                <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">This can take a moment if modems are initializing. Please ensure they are properly connected. You can also try refreshing.</p>
              </div>
          )}
        </div>
      );
    }

    if (error) {
       return (
         <div className="text-center py-10 bg-destructive/10 border border-destructive/20 rounded-lg">
            <AlertTriangle className="mx-auto h-12 w-12 text-destructive mb-4" />
            <p className="text-xl text-destructive/90 font-semibold">Could not load modem data</p>
            <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">{error}</p>
          </div>
       );
    }

    if (modems.length === 0 && !isLoading) {
       return (
         <div className="text-center py-10">
            <Wifi className="mx-auto h-12 w-12 text-muted-foreground" />
            <p className="text-xl text-muted-foreground">No modems found.</p>
             <p className="text-sm text-muted-foreground mt-2">Please connect a USB modem to continue.</p>
          </div>
      );
    }

    return (
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {modems.map((modem) => (
          <ModemStatusCard key={modem.id} initialModem={modem} onNameUpdate={handleNameUpdate} />
        ))}
      </div>
    );
  }

  return (
    <>
      <PageHeader
        title="Modem Status"
        description="Monitor the status and IP addresses of your USB modems. Click the modem name to edit it."
        actions={
          <Button onClick={() => fetchModems(true)} disabled={isLoading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh All
          </Button>
        }
      />
      {renderContent()}
    </>
  );
}
