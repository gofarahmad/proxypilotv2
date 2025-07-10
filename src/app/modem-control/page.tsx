
'use client';

import { useState, useEffect, useCallback } from 'react';
import { PageHeader } from '@/components/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useToast } from '@/hooks/use-toast';
import { getAllModemStatuses, ModemStatus } from '@/services/network-service';
import { sendSms, readSms, sendUssd, SmsMessage } from '@/services/modem-actions-service';
import { Loader2, Send, MessageSquare, Asterisk, RefreshCw, Smartphone, AlertTriangle } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';

export default function ModemControlPage() {
    const [modems, setModems] = useState<ModemStatus[]>([]);
    const [selectedInterface, setSelectedInterface] = useState<string>('');
    const [isLoadingModems, setIsLoadingModems] = useState(true);
    const [isSendingSms, setIsSendingSms] = useState(false);
    const [isReadingSms, setIsReadingSms] = useState(false);
    const [isSendingUssd, setIsSendingUssd] = useState(false);

    const [recipient, setRecipient] = useState('');
    const [smsContent, setSmsContent] = useState('');
    const [ussdCode, setUssdCode] = useState('');

    const [receivedSms, setReceivedSms] = useState<SmsMessage[]>([]);
    const [ussdResponse, setUssdResponse] = useState<string>('');

    const { toast } = useToast();

    const fetchModems = useCallback(async () => {
        setIsLoadingModems(true);
        try {
            const modemData = await getAllModemStatuses();
            // Filter only for modems that are managed by mmcli
            const supportedModems = modemData.filter(m => m.source === 'mmcli_enhanced' && m.status === 'connected');
            setModems(supportedModems);

            if (supportedModems.length > 0 && !selectedInterface) {
                setSelectedInterface(supportedModems[0].interfaceName);
            } else if (supportedModems.length > 0 && !supportedModems.some(m => m.interfaceName === selectedInterface)) {
                // if the selected modem is no longer available, select the first one
                setSelectedInterface(supportedModems[0].interfaceName);
            } else if (supportedModems.length === 0) {
                setSelectedInterface('');
            }
        } catch (error) {
            toast({ title: 'Error', description: 'Failed to load modem list.', variant: 'destructive' });
        } finally {
            setIsLoadingModems(false);
        }
    }, [toast, selectedInterface]);

    useEffect(() => {
        fetchModems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleReadSms = useCallback(async () => {
        if (!selectedInterface) return;
        setIsReadingSms(true);
        try {
            const messages = await readSms(selectedInterface);
            setReceivedSms(messages);
             if (messages.length === 0) {
                toast({ title: 'No New Messages', description: `No SMS found on ${selectedInterface}.` });
            }
        } catch (error) {
            toast({ title: 'Error Reading SMS', description: String(error), variant: 'destructive' });
        } finally {
            setIsReadingSms(false);
        }
    }, [selectedInterface, toast]);
    
    // Auto-read SMS when interface changes
    useEffect(() => {
        if(selectedInterface){
            setReceivedSms([]);
            setUssdResponse('');
            handleReadSms();
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedInterface]);


    const handleSendSms = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!selectedInterface) return;
        setIsSendingSms(true);
        try {
            const result = await sendSms(selectedInterface, recipient, smsContent);
            toast({
                title: result.success ? 'SMS Sent' : 'SMS Failed',
                description: result.message,
                variant: result.success ? 'default' : 'destructive',
            });
            if (result.success) {
                setRecipient('');
                setSmsContent('');
            }
        } catch (error) {
            toast({ title: 'Error', description: String(error), variant: 'destructive' });
        } finally {
            setIsSendingSms(false);
        }
    };

    const handleSendUssd = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!selectedInterface) return;
        setIsSendingUssd(true);
        setUssdResponse('');
        try {
            const result = await sendUssd(selectedInterface, ussdCode);
            setUssdResponse(result.response);
            toast({
                title: result.success ? 'USSD Response' : 'USSD Failed',
                description: result.response.split('\n')[0], // Show first line in toast
                variant: result.success ? 'default' : 'destructive',
            });
        } catch (error) {
            toast({ title: 'Error', description: String(error), variant: 'destructive' });
        } finally {
            setIsSendingUssd(false);
        }
    };
    
    return (
        <>
            <PageHeader
                title="Modem Actions"
                description="Send SMS messages and USSD commands directly through your modems."
            />
            
            {!isLoadingModems && modems.length === 0 && (
                 <Card className="mb-6 bg-yellow-400/20 border-yellow-500/50">
                    <CardHeader className="flex flex-row items-center gap-4 space-y-0">
                        <AlertTriangle className="h-8 w-8 text-yellow-600"/>
                        <div>
                            <CardTitle>Feature Not Available</CardTitle>
                            <CardDescription className="text-yellow-700/80">
                                This feature requires a modem to be managed by ModemManager (`mmcli`). No such modems are currently detected.
                            </CardDescription>
                        </div>
                    </CardHeader>
                </Card>
            )}

            <div className="grid gap-6 md:grid-cols-3">
                <div className="md:col-span-1">
                    <Card>
                        <CardHeader>
                            <CardTitle>Select Modem</CardTitle>
                             <CardDescription>Choose an active modem to perform actions.</CardDescription>
                        </CardHeader>
                        <CardContent>
                             {isLoadingModems ? (
                                <Skeleton className="h-10 w-full" />
                            ) : (
                            <Select
                                onValueChange={setSelectedInterface}
                                value={selectedInterface}
                                disabled={modems.length === 0}
                            >
                                <SelectTrigger>
                                    <SelectValue placeholder="Select a supported modem" />
                                </SelectTrigger>
                                <SelectContent>
                                    {modems.map((modem) => (
                                        <SelectItem key={modem.interfaceName} value={modem.interfaceName}>
                                            {modem.name} ({modem.interfaceName})
                                        </SelectItem>
                                    ))}
                                    {modems.length === 0 && <SelectItem value="no-modems" disabled>No supported modems found</SelectItem>}
                                </SelectContent>
                            </Select>
                            )}
                        </CardContent>
                    </Card>
                </div>

                <div className="md:col-span-2">
                    <Tabs defaultValue="sms" className="w-full">
                        <TabsList className="grid w-full grid-cols-2">
                            <TabsTrigger value="sms" disabled={!selectedInterface}><MessageSquare className="mr-2 h-4 w-4" />SMS</TabsTrigger>
                            <TabsTrigger value="ussd" disabled={!selectedInterface}><Asterisk className="mr-2 h-4 w-4" />USSD</TabsTrigger>
                        </TabsList>
                        
                        {/* SMS Tab */}
                        <TabsContent value="sms">
                            <Card>
                                <CardHeader>
                                    <CardTitle>Send & Read SMS</CardTitle>
                                    <CardDescription>Compose a new SMS or view received messages on the selected modem.</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-6">
                                    <form onSubmit={handleSendSms} className="space-y-4 p-4 border rounded-lg">
                                        <h3 className="font-semibold text-lg flex items-center"><Send className="mr-2 h-5 w-5"/>New Message</h3>
                                        <div className="space-y-2">
                                            <Label htmlFor="recipient">Recipient</Label>
                                            <Input id="recipient" value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="e.g., +6281234567890" disabled={!selectedInterface} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="sms-content">Message</Label>
                                            <Textarea id="sms-content" value={smsContent} onChange={(e) => setSmsContent(e.target.value)} placeholder="Type your message here..." disabled={!selectedInterface} />
                                        </div>
                                        <Button type="submit" disabled={!selectedInterface || isSendingSms}>
                                            {isSendingSms && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                            Send SMS
                                        </Button>
                                    </form>

                                    <div className="space-y-4">
                                        <div className="flex justify-between items-center">
                                            <h3 className="font-semibold text-lg">Received Messages</h3>
                                            <Button variant="outline" size="sm" onClick={handleReadSms} disabled={!selectedInterface || isReadingSms}>
                                                {isReadingSms ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                                                Refresh
                                            </Button>
                                        </div>
                                        <div className="space-y-3 max-h-80 overflow-y-auto p-4 bg-muted/50 rounded-lg">
                                            {isReadingSms ? (
                                                <div className="flex items-center justify-center p-4"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
                                            ) : receivedSms.length > 0 ? (
                                                receivedSms.map(sms => (
                                                    <div key={sms.id} className="p-3 bg-background rounded shadow">
                                                        <div className="flex justify-between items-baseline">
                                                            <p className="font-bold text-sm">{sms.from}</p>
                                                            <p className="text-xs text-muted-foreground">{new Date(sms.timestamp).toLocaleString()}</p>
                                                        </div>
                                                        <p className="mt-1 text-sm">{sms.content}</p>
                                                    </div>
                                                ))
                                            ) : (
                                                <p className="text-sm text-center text-muted-foreground py-4">No messages found on this modem.</p>
                                            )}
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* USSD Tab */}
                        <TabsContent value="ussd">
                            <Card>
                                <CardHeader>
                                    <CardTitle>Send USSD Command</CardTitle>
                                    <CardDescription>Check balance, subscribe to packages, etc. (e.g., *123#).</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-6">
                                    <form onSubmit={handleSendUssd} className="space-y-4">
                                         <div className="space-y-2">
                                            <Label htmlFor="ussd-code">USSD Code</Label>
                                            <Input id="ussd-code" value={ussdCode} onChange={(e) => setUssdCode(e.target.value)} placeholder="e.g., *123#" disabled={!selectedInterface}/>
                                        </div>
                                        <Button type="submit" disabled={!selectedInterface || isSendingUssd}>
                                            {isSendingUssd && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                            Send Command
                                        </Button>
                                    </form>
                                    {ussdResponse && (
                                        <div className="space-y-2">
                                            <h3 className="font-semibold">Response:</h3>
                                            <div className="p-4 bg-muted rounded-md font-mono text-sm whitespace-pre-wrap">
                                                {isSendingUssd ? <Loader2 className="h-5 w-5 animate-spin"/> : ussdResponse}
                                            </div>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </TabsContent>
                    </Tabs>
                </div>
            </div>
        </>
    );
}
