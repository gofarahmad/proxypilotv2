
'use client';

import React from 'react';
import { PageHeader } from '@/components/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { RotateCcw, RefreshCw, Loader2, Wifi, Settings2, TimerIcon, AlertTriangle } from 'lucide-react';
import { useState, useEffect, useCallback, useRef } from 'react';
import { useToast } from '@/hooks/use-toast';
import { Skeleton } from '@/components/ui/skeleton';
import type { ModemStatus } from '@/services/network-service';
import { getAllModemStatuses, rotateIp as serviceRotateIp } from '@/services/network-service';
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Separator } from '@/components/ui/separator';

interface RotatableModem extends ModemStatus {
  rotating: boolean;
  lastRotated?: Date;
  autoRotateEnabled: boolean;
  autoRotateIntervalMinutes: number;
}

export default function IpRotationPage() {
  const [modems, setModems] = useState<RotatableModem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const { toast } = useToast();
  const [modemAutoRotateCountdowns, setModemAutoRotateCountdowns] = useState<Record<string, number>>({});
  const modemTimersRef = useRef<Record<string, { rotationTimer?: NodeJS.Timeout; countdownTimer?: NodeJS.Timeout }>>({});

  const fetchModemsData = useCallback(async () => {
    setIsLoading(true);
    try {
      const modemData = await getAllModemStatuses();
      setModems(prevModems => {
        // Preserve auto-rotate settings from previous state
        const settingsMap = new Map(prevModems.map(m => [m.interfaceName, { autoRotateEnabled: m.autoRotateEnabled, autoRotateIntervalMinutes: m.autoRotateIntervalMinutes }]));
        return modemData.map(newModem => ({
          ...newModem,
          rotating: false,
          autoRotateEnabled: settingsMap.get(newModem.interfaceName)?.autoRotateEnabled || false,
          autoRotateIntervalMinutes: settingsMap.get(newModem.interfaceName)?.autoRotateIntervalMinutes || 10,
        }));
      });
    } catch (error) {
      toast({ title: 'Error fetching modems', description: String(error), variant: 'destructive' });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchModemsData();
    // Cleanup timers on unmount
    return () => {
      Object.values(modemTimersRef.current).forEach(timers => {
        if (timers.rotationTimer) clearInterval(timers.rotationTimer);
        if (timers.countdownTimer) clearInterval(timers.countdownTimer);
      });
      modemTimersRef.current = {};
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRotateIp = useCallback(async (interfaceName: string, isAutoRotate: boolean = false) => {
    setModems(prev => prev.map(m => m.interfaceName === interfaceName ? { ...m, rotating: true } : m));
    
    try {
      const newIp = await serviceRotateIp(interfaceName);
      toast({
        title: `IP ${isAutoRotate ? 'Auto-' : ''}Rotated for ${interfaceName}`,
        description: `New IP: ${newIp}`,
      });
      
      setModems(prev => {
        const modemInState = prev.find(m => m.interfaceName === interfaceName);
        // This part needs to access the latest state, which can be tricky in closures.
        // We'll reset the countdown via the main `useEffect` for modems.
        return prev.map(m => 
            m.interfaceName === interfaceName 
            ? { ...m, ipAddress: newIp, status: 'connected', lastRotated: new Date(), rotating: false } 
            : m
        );
      });

    } catch (error) {
      toast({ title: `Error ${isAutoRotate ? 'Auto-' : ''}Rotating IP for ${interfaceName}`, description: String(error), variant: 'destructive' });
       setModems(prev => prev.map(m => m.interfaceName === interfaceName ? { ...m, rotating: false } : m));
    }
  }, [toast]);
  
  const handleRotateAll = useCallback(async () => {
    const connectedModems = modems.filter(m => m.status === 'connected' && m.source === 'mmcli_enhanced');
    if (connectedModems.length === 0) {
      toast({ title: "Rotation Skipped", description: "No connected modems managed by ModemManager to rotate.", variant: "default" });
      return;
    }

    toast({ title: "Mass IP Rotation Started", description: `Attempting to rotate IPs for ${connectedModems.length} supported modem(s).` });
    setModems(prev => prev.map(m => connectedModems.find(cm => cm.interfaceName === m.interfaceName) ? { ...m, rotating: true } : m));
    
    const rotationPromises = connectedModems
      .map(m => serviceRotateIp(m.interfaceName)
        .then(newIp => ({ interfaceName: m.interfaceName, name: m.name, newIp, success: true }))
        .catch(err => ({ interfaceName: m.interfaceName, name: m.name, error: String(err), success: false }))
      );
      
    const results = await Promise.all(rotationPromises);
    
    results.forEach(result => {
      if (result.success) {
        toast({ title: `IP Rotated for ${result.name}`, description: `New IP: ${result.newIp}` });
      } else {
        toast({ title: `Error Rotating IP for ${result.name}`, description: result.error, variant: 'destructive' });
      }
    });
    
    await fetchModemsData();
  }, [toast, modems, fetchModemsData]);

  useEffect(() => {
    modems.forEach((modem) => {
      const timerKey = modem.interfaceName;

      // Clear existing timers for this modem before re-evaluating
      if (modemTimersRef.current[timerKey]) {
        clearInterval(modemTimersRef.current[timerKey].rotationTimer);
        clearInterval(modemTimersRef.current[timerKey].countdownTimer);
        delete modemTimersRef.current[timerKey];
      }

      if (modem.autoRotateEnabled && modem.autoRotateIntervalMinutes > 0 && modem.status === 'connected' && modem.source === 'mmcli_enhanced') {
        const intervalMs = modem.autoRotateIntervalMinutes * 60 * 1000;
        
        // Initialize countdown if it's not set
        if (modemAutoRotateCountdowns[timerKey] === undefined) {
             setModemAutoRotateCountdowns(prev => ({ ...prev, [timerKey]: intervalMs / 1000 }));
        }

        const rotationTimer = setInterval(() => handleRotateIp(modem.interfaceName, true), intervalMs);

        const countdownTimer = setInterval(() => {
          setModemAutoRotateCountdowns(prev => {
            const currentCountdown = prev[timerKey] || 0;
            if (currentCountdown <= 1) { // When it hits 0, reset based on modem state
                 const currentModem = modems.find(m => m.interfaceName === timerKey);
                 return { ...prev, [timerKey]: (currentModem?.autoRotateIntervalMinutes || 0) * 60 };
            }
            return { ...prev, [timerKey]: currentCountdown - 1 };
          });
        }, 1000);

        modemTimersRef.current[timerKey] = { rotationTimer, countdownTimer };
      } else {
        // If auto-rotate is disabled, clear the countdown from state
         if(modemAutoRotateCountdowns[timerKey] !== undefined){
            setModemAutoRotateCountdowns(prev => {
                const newState = {...prev};
                delete newState[timerKey];
                return newState;
            });
         }
      }
    });

    // Cleanup function for useEffect
    return () => {
        Object.values(modemTimersRef.current).forEach(timers => {
            if(timers.rotationTimer) clearInterval(timers.rotationTimer);
            if(timers.countdownTimer) clearInterval(timers.countdownTimer);
        });
    }

  }, [modems, handleRotateIp, modemAutoRotateCountdowns]);

  const handleTogglePerModemAutoRotate = (interfaceName: string, enabled: boolean) => {
    setModems(prevModems => prevModems.map(m => {
      if (m.interfaceName === interfaceName) {
        if (enabled && m.autoRotateIntervalMinutes <= 0) {
          toast({ title: "Invalid Interval", description: "Please set a positive rotation interval (minutes).", variant: "destructive" });
          return { ...m, autoRotateEnabled: false };
        }
        if (enabled) {
          setModemAutoRotateCountdowns(prev => ({ ...prev, [interfaceName]: m.autoRotateIntervalMinutes * 60 }));
        }
        return { ...m, autoRotateEnabled: enabled };
      }
      return m;
    }));
  };

  const handlePerModemIntervalChange = (interfaceName: string, value: string) => {
    const interval = Math.max(1, parseInt(value) || 1);
    setModems(prevModems => prevModems.map(m => {
      if (m.interfaceName === interfaceName) {
        if (m.autoRotateEnabled) {
          setModemAutoRotateCountdowns(prev => ({ ...prev, [interfaceName]: interval * 60 }));
        }
        return { ...m, autoRotateIntervalMinutes: interval };
      }
      return m;
    }));
  };
  
  const isRotationSupported = (modem: RotatableModem) => modem.source === 'mmcli_enhanced';

  return (
    <>
      <PageHeader
        title="IP Rotation"
        description="Manually or automatically rotate IP addresses for your modem interfaces."
        actions={
          <>
            <Button onClick={fetchModemsData} disabled={isLoading} variant="outline">
              <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh List
            </Button>
            <Button onClick={handleRotateAll} disabled={isLoading || modems.every(m => m.status !== 'connected' || !isRotationSupported(m))}>
              <RotateCcw className="mr-2 h-4 w-4" />
              Rotate All Supported
            </Button>
          </>
        }
      />

      {isLoading && modems.length === 0 ? (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-[420px] w-full rounded-lg" />)}
        </div>
      ) : modems.length === 0 && !isLoading ? (
         <div className="text-center py-10">
            <Wifi className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-xl text-muted-foreground">No modems available for IP rotation.</p>
            <p className="text-sm text-muted-foreground mt-2">Connect modems to see them here.</p>
          </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
          {modems.map((modem) => (
            <Card key={modem.interfaceName} className={`shadow-md flex flex-col ${!isRotationSupported(modem) ? 'bg-muted/30' : ''}`}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">{modem.name}</CardTitle>
                  <RotateCcw className={`h-5 w-5 ${isRotationSupported(modem) ? 'text-primary' : 'text-muted-foreground'}`} />
                </div>
                <CardDescription>Interface: {modem.interfaceName}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 flex-grow">
                <p className="text-sm">Current IP: <span className="font-semibold">{modem.ipAddress || 'N/A'}</span></p>
                <p className="text-xs text-muted-foreground">Status: {modem.status}</p>
                {modem.lastRotated && <p className="text-xs text-muted-foreground">Last Rotated: {new Date(modem.lastRotated).toLocaleString()}</p>}
                
                {!isRotationSupported(modem) && (
                  <div className="p-2 text-xs text-center bg-yellow-400/20 text-yellow-700 rounded-md flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                    IP Rotation requires the modem to be managed by ModemManager.
                  </div>
                )}
                
                <Button 
                  onClick={() => handleRotateIp(modem.interfaceName, false)} 
                  disabled={modem.rotating || modem.status !== 'connected' || isLoading || !isRotationSupported(modem)}
                  className="w-full"
                  variant="outline"
                  title={!isRotationSupported(modem) ? 'Modem not managed by ModemManager' : (modem.status !== 'connected' ? 'Modem not connected' : (modem.rotating ? 'Rotation in progress' : 'Rotate IP Manually'))}
                >
                  {modem.rotating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RotateCcw className="mr-2 h-4 w-4" />}
                  Rotate IP Manually
                </Button>
                
                <Separator className="my-4" />

                <div className="space-y-3 pt-2">
                    <div className="flex items-center justify-between">
                        <Label htmlFor={`auto-rotate-${modem.interfaceName}`} className={`text-base font-medium flex items-center ${!isRotationSupported(modem) ? 'text-muted-foreground' : ''}`}>
                            <TimerIcon className="mr-2 h-5 w-5 text-muted-foreground"/> Auto Rotate this Modem
                        </Label>
                        <Switch
                            id={`auto-rotate-${modem.interfaceName}`}
                            checked={modem.autoRotateEnabled}
                            onCheckedChange={(checked) => handleTogglePerModemAutoRotate(modem.interfaceName, checked)}
                            disabled={modem.status !== 'connected' || !isRotationSupported(modem)}
                            aria-label={`Toggle automatic IP rotation for ${modem.name}`}
                        />
                    </div>
                    {modem.autoRotateEnabled && isRotationSupported(modem) && (
                    <div className="pl-2 space-y-2">
                        <div>
                            <Label htmlFor={`interval-${modem.interfaceName}`} className="text-xs text-muted-foreground">Interval (minutes)</Label>
                            <Input
                                id={`interval-${modem.interfaceName}`}
                                type="number"
                                value={modem.autoRotateIntervalMinutes}
                                onChange={(e) => handlePerModemIntervalChange(modem.interfaceName, e.target.value)}
                                min="1"
                                className="w-full text-sm h-8 mt-1"
                                aria-label={`Rotation interval in minutes for ${modem.name}`}
                                disabled={modem.status !== 'connected'}
                            />
                        </div>
                        {modem.status === 'connected' && modemAutoRotateCountdowns[modem.interfaceName] !== undefined && (
                             <p className="text-xs text-muted-foreground pt-1">
                                Next auto rotation in: <span className="font-semibold text-primary">{Math.floor(modemAutoRotateCountdowns[modem.interfaceName] / 60)}m {modemAutoRotateCountdowns[modem.interfaceName] % 60}s</span>
                            </p>
                        )}
                         {modem.status !== 'connected' && (
                            <p className="text-xs text-destructive pt-1">Modem must be connected for auto-rotation.</p>
                        )}
                    </div>
                    )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
