
'use client';

import type { ModemStatus } from '@/services/network-service';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Wifi, WifiOff, AlertCircle, RefreshCw, Loader2, Pencil, Power, Globe, Signal, Tag, Shield, BarChart } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useToast } from '@/hooks/use-toast';
import { getModemStatus as fetchModemStatus } from '@/services/network-service';
import { useState, useEffect, useCallback, useRef } from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';

interface ModemStatusCardProps {
  initialModem: ModemStatus;
  onNameUpdate: (interfaceName: string, newName: string) => void;
}

export function ModemStatusCard({ initialModem, onNameUpdate }: ModemStatusCardProps) {
  const [modem, setModem] = useState<ModemStatus>(initialModem);
  const [isLoading, setIsLoading] = useState(false);
  const [isEditingName, setIsEditingName] = useState(false);
  const [editingName, setEditingName] = useState(initialModem.name);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();

  const refreshStatus = useCallback(async () => {
    setIsLoading(true);
    try {
      const updatedStatus = await fetchModemStatus(modem.interfaceName);
      setModem(updatedStatus);
      if (updatedStatus.name !== editingName && !isEditingName) {
        setEditingName(updatedStatus.name);
      }
    } catch (error) {
      toast({ title: 'Error', description: `Failed to refresh status for ${modem.name}`, variant: 'destructive' });
    } finally {
      setIsLoading(false);
    }
  }, [modem.interfaceName, modem.name, toast, editingName, isEditingName]);
  
  useEffect(() => {
    setModem(initialModem);
    setEditingName(initialModem.name);
  }, [initialModem]);

  useEffect(() => {
    if (isEditingName && nameInputRef.current) {
      nameInputRef.current.focus();
      nameInputRef.current.select();
    }
  }, [isEditingName]);

  const handleNameEditSubmit = () => {
    if (editingName.trim() && editingName !== modem.name) {
      onNameUpdate(modem.interfaceName, editingName.trim());
    }
    setIsEditingName(false);
  };
  
  if (!modem) return <Skeleton className="h-[420px] w-full" />;

  const isConnected = modem.status === 'connected';
  const Icon = isConnected ? Wifi : modem.status === 'disconnected' ? WifiOff : AlertCircle;

  return (
    <Card className="shadow-md hover:shadow-lg transition-shadow flex flex-col">
      <CardHeader>
        <div className="flex items-start justify-between">
          {isEditingName ? (
            <Input
              ref={nameInputRef}
              value={editingName}
              onChange={(e) => setEditingName(e.target.value)}
              onBlur={handleNameEditSubmit}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleNameEditSubmit();
                if (e.key === 'Escape') {
                  setEditingName(modem.name);
                  setIsEditingName(false);
                }
              }}
              className="text-xl font-semibold p-0 h-auto border-0 focus-visible:ring-0 focus-visible:ring-offset-0"
            />
          ) : (
            <CardTitle 
              className="text-xl flex items-center gap-2 cursor-pointer group"
              onClick={() => setIsEditingName(true)}
              title="Click to edit name"
            >
              {modem.name}
              <Pencil className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
            </CardTitle>
          )}
          <Icon className={cn('h-6 w-6 shrink-0 ml-2', isConnected ? 'text-green-500' : 'text-red-500')} />
        </div>
        <CardDescription>Interface: {modem.interfaceName}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 flex-grow flex flex-col">
        <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Status:</span>
              <Badge variant={isConnected ? 'default' : 'destructive'} className={cn(isConnected ? 'bg-green-500/20 text-green-700 border-green-500' : 'bg-red-500/20 text-red-700 border-red-500')}>
                {modem.status}
              </Badge>
            </div>
             <div className="flex items-center justify-between">
              <span className="text-sm font-medium flex items-center gap-1"><Tag className="h-4 w-4 text-blue-500"/> Operator:</span>
              <span className="text-sm font-semibold">{modem.details?.operator || 'N/A'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium flex items-center gap-1"><Shield className="h-4 w-4 text-gray-500"/> IMEI:</span>
              <span className="text-sm font-mono">{modem.details?.imei || 'N/A'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium flex items-center gap-1"><Signal className="h-4 w-4 text-orange-500"/> RSSI:</span>
              <span className="text-sm font-mono">{modem.details?.rssi || 'N/A'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium flex items-center gap-1"><BarChart className="h-4 w-4 text-purple-500"/> RSRP/SINR:</span>
              <span className="text-sm font-mono">{modem.details?.rsrp || 'N/A'} / {modem.details?.sinr || 'N/A'}</span>
            </div>
            <div className="flex items-center justify-between pt-2">
              <span className="text-sm font-medium">Proxy Status:</span>
              
                <Badge variant={modem.proxyStatus === 'running' ? 'default' : 'secondary'} 
                       className={cn(modem.proxyStatus === 'running' ? 'bg-blue-500/20 text-blue-700 border-blue-500' : 'bg-gray-500/20 text-gray-700 border-gray-500')}>
                  <Power className="mr-1 h-3 w-3" />
                  {modem.proxyStatus}
                </Badge>
             
            </div>
        </div>
        
        <div className="flex-grow"></div>

        <div className="space-y-2 pt-2">
            <Button onClick={refreshStatus} disabled={isLoading} size="sm" variant="outline" className="w-full">
              {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
               Refresh Status
            </Button>
        </div>
      </CardContent>
    </Card>
  );
}

    