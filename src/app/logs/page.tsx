
'use client';

import { PageHeader } from '@/components/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { BarChart3, Loader2, ServerCrash } from 'lucide-react';
import { useEffect, useState } from 'react';
import { getSystemLogs, LogEntry } from '@/services/system-service';
import { useToast } from '@/hooks/use-toast';
import { Button } from '@/components/ui/button';
import { RefreshCw } from 'lucide-react';

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  const fetchLogs = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const fetchedLogs = await getSystemLogs();
      setLogs(fetchedLogs.reverse()); // Reverse to show most recent first
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "An unknown error occurred";
      setError(errorMessage);
      toast({
        title: 'Error Fetching Logs',
        description: errorMessage,
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const getLogLevelClass = (level: string) => {
    switch (level.toUpperCase()) {
      case 'ERROR':
        return 'text-red-500';
      case 'WARN':
        return 'text-yellow-600';
      case 'INFO':
        return 'text-blue-600';
      case 'DEBUG':
        return 'text-gray-500';
      default:
        return 'text-foreground';
    }
  };
  
    const getLogLevelBadgeClass = (level: string) => {
    switch (level.toUpperCase()) {
      case 'ERROR':
        return 'text-red-700 border-red-500 bg-red-500/10';
      case 'WARN':
        return 'text-yellow-700 border-yellow-500 bg-yellow-500/10';
      case 'INFO':
        return 'text-blue-700 border-blue-500 bg-blue-500/10';
      default:
        return 'text-gray-700 border-gray-500 bg-gray-500/10';
    }
  };


  return (
    <>
      <PageHeader
        title="System Logs"
        description="View real-time activity logs, errors, and important system events from the backend."
        actions={
            <Button onClick={fetchLogs} disabled={isLoading} variant="outline">
                <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                Refresh Logs
            </Button>
        }
      />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center">
            <BarChart3 className="mr-2 h-6 w-6 text-primary" />
            Recent Log Entries
          </CardTitle>
          <CardDescription>
            Showing the latest events from the server. Most recent entries are at the top.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="max-h-[600px] overflow-y-auto rounded-md border bg-muted/20 p-4 font-mono text-xs">
            {isLoading ? (
              <div className="flex items-center justify-center p-8">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            ) : error ? (
                <div className="text-center py-10 text-destructive">
                    <ServerCrash className="mx-auto h-10 w-10 mb-2" />
                    <p className="font-semibold">Failed to load logs</p>
                    <p className="text-xs mt-1">{error}</p>
                </div>
            ) : logs.length === 0 ? (
                <p className="text-center text-muted-foreground py-10">No log entries found.</p>
            ) : (
              logs.map((log, index) => (
                <div key={index} className="flex items-start space-x-3 mb-1 p-1 rounded">
                  <span className="text-muted-foreground tabular-nums">[{new Date(log.timestamp).toLocaleString()}]</span>
                  <span className={`font-bold w-12 text-center px-1 rounded-sm ${getLogLevelBadgeClass(log.level)}`}>{log.level}</span>
                  <span className="flex-1 whitespace-pre-wrap break-words">{log.message}</span>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </>
  );
}
