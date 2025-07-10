'use client';

import { useState, useEffect, useCallback } from 'react';
import { PageHeader } from '@/components/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { getNetworkInterfaces, getStatsForInterface, VnstatData } from '@/services/stats-service';
import { Skeleton } from '@/components/ui/skeleton';
import { RefreshCw, AreaChart, AlertTriangle, Loader2 } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";


function formatBytes(kib: number): string {
  if (kib === 0) return '0 B';
  const units = ['KiB', 'MiB', 'GiB', 'TiB'];
  const i = Math.floor(Math.log(kib) / Math.log(1024));
  return `${(kib / Math.pow(1024, i)).toFixed(2)} ${units[i]}`;
}

const StatsTable = ({ title, data }: { title: string, data: { rx: number, tx: number, date: { year: number, month: number, day?: number, hour?: number } }[] }) => {
    if (!data || data.length === 0) {
        return <p className="text-sm text-muted-foreground text-center py-4">No {title.toLowerCase()} data available for this interface.</p>;
    }

    const formatLabel = (item: any) => {
        if(item.hour !== undefined) return `${item.date.year}-${String(item.date.month).padStart(2, '0')}-${String(item.date.day).padStart(2, '0')} ${String(item.hour).padStart(2, '0')}:00`;
        if(item.day !== undefined) return `${item.date.year}-${String(item.date.month).padStart(2, '0')}-${String(item.date.day).padStart(2, '0')}`;
        return `${item.date.year}-${String(item.date.month).padStart(2, '0')}`;
    }

    return (
        <Table>
            <TableHeader>
                <TableRow>
                    <TableHead>{title}</TableHead>
                    <TableHead className="text-right">Received (RX)</TableHead>
                    <TableHead className="text-right">Transmitted (TX)</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                </TableRow>
            </TableHeader>
            <TableBody>
                {data.map((item, index) => (
                    <TableRow key={index}>
                        <TableCell className="font-medium">{formatLabel(item)}</TableCell>
                        <TableCell className="text-right">{formatBytes(item.rx)}</TableCell>
                        <TableCell className="text-right">{formatBytes(item.tx)}</TableCell>
                        <TableCell className="text-right font-semibold">{formatBytes(item.rx + item.tx)}</TableCell>
                    </TableRow>
                ))}
            </TableBody>
        </Table>
    );
};


export default function NetworkStatsPage() {
  const [interfaces, setInterfaces] = useState<string[]>([]);
  const [selectedInterface, setSelectedInterface] = useState<string>('');
  const [stats, setStats] = useState<VnstatData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isStatsLoading, setIsStatsLoading] = useState(false);
  const { toast } = useToast();

  const fetchInterfaces = useCallback(async () => {
    setIsLoading(true);
    try {
      const ifs = await getNetworkInterfaces();
      setInterfaces(ifs);
      if (ifs.length > 0) {
        setSelectedInterface(ifs[0]);
      }
    } catch (error) {
      toast({ title: "Error", description: "Could not fetch network interfaces.", variant: "destructive" });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchInterfaces();
  }, [fetchInterfaces]);

  useEffect(() => {
    if (selectedInterface) {
      const fetchStats = async () => {
        setIsStatsLoading(true);
        try {
          const data = await getStatsForInterface(selectedInterface);
          setStats(data);
        } catch (error) {
           toast({ title: `Error fetching stats for ${selectedInterface}`, description: error instanceof Error ? error.message : "Unknown error", variant: "destructive" });
           setStats(null);
        } finally {
            setIsStatsLoading(false);
        }
      };
      fetchStats();
    }
  }, [selectedInterface, toast]);

  return (
    <>
      <PageHeader
        title="Network Statistics"
        description="Monitor network traffic and data usage for your interfaces using vnstat."
        actions={
          <Button onClick={fetchInterfaces} disabled={isLoading} variant="outline">
            <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh Interfaces
          </Button>
        }
      />
      
      <div className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Interface Selection</CardTitle>
            <CardDescription>Select a network interface to view its traffic statistics.</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
                <Skeleton className="h-10 w-full md:w-1/3" />
            ) : (
                <Select
                    onValueChange={setSelectedInterface}
                    value={selectedInterface}
                    disabled={interfaces.length === 0}
                >
                    <SelectTrigger className="w-full md:w-1/3">
                        <SelectValue placeholder="Select an interface..." />
                    </SelectTrigger>
                    <SelectContent>
                        {interfaces.map((iface) => (
                            <SelectItem key={iface} value={iface}>
                                {iface}
                            </SelectItem>
                        ))}
                        {interfaces.length === 0 && <SelectItem value="no-interfaces" disabled>No monitored interfaces found</SelectItem>}
                    </SelectContent>
                </Select>
            )}
          </CardContent>
        </Card>

        {isStatsLoading ? (
            <Card>
                <CardHeader>
                    <Skeleton className="h-6 w-48"/>
                    <Skeleton className="h-4 w-64 mt-2"/>
                </CardHeader>
                <CardContent className="pt-4">
                    <Skeleton className="h-40 w-full" />
                </CardContent>
            </Card>
        ) : selectedInterface && stats ? (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center">
                        <AreaChart className="mr-2 h-6 w-6 text-primary" />
                        Traffic for {stats.name}
                    </CardTitle>
                    <CardDescription>
                        Total Received (RX): <span className="font-bold">{formatBytes(stats.totalrx)}</span> | 
                        Total Transmitted (TX): <span className="font-bold">{formatBytes(stats.totaltx)}</span>
                    </CardDescription>
                </CardHeader>
                <CardContent>
                   <Tabs defaultValue="daily" className="w-full">
                        <TabsList>
                            <TabsTrigger value="daily">Daily</TabsTrigger>
                            <TabsTrigger value="monthly">Monthly</TabsTrigger>
                            <TabsTrigger value="hourly">Hourly</TabsTrigger>
                        </TabsList>
                        <TabsContent value="daily">
                           <StatsTable title="Date" data={stats.day} />
                        </TabsContent>
                        <TabsContent value="monthly">
                           <StatsTable title="Month" data={stats.month} />
                        </TabsContent>
                        <TabsContent value="hourly">
                           <StatsTable title="Hour" data={stats.hour} />
                        </TabsContent>
                    </Tabs>
                </CardContent>
            </Card>
        ) : selectedInterface ? (
            <Card className="bg-yellow-400/20 border-yellow-500/50">
                <CardHeader className="flex-row items-center gap-4 space-y-0">
                    <AlertTriangle className="h-8 w-8 text-yellow-600"/>
                    <div>
                        <CardTitle>Data Not Available</CardTitle>
                        <CardDescription className="text-yellow-700/80">
                            Could not load statistics for {selectedInterface}. `vnstat` might not have data for this interface yet, or an error occurred.
                        </CardDescription>
                    </div>
                </CardHeader>
            </Card>
        ) : null}
      </div>
    </>
  );
}
