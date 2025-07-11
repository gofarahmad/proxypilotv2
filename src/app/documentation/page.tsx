
import { PageHeader } from '@/components/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { AlertCircle, Wifi, Network, RotateCcw, Smartphone, HelpCircle } from 'lucide-react';

export default function DocumentationPage() {
  return (
    <>
      <PageHeader
        title="Documentation & Guides"
        description="A central place for understanding how Proxy Pilot works and best practices."
      />
      <Card>
        <CardHeader>
          <CardTitle>Frequently Asked Questions</CardTitle>
          <CardDescription>
            Click on a topic below to expand it and learn more.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Accordion type="single" collapsible className="w-full">
            <AccordionItem value="item-hilink">
              <AccordionTrigger>
                <div className="flex items-center gap-2 font-bold text-indigo-600">
                  <HelpCircle className="h-5 w-5" />
                  <span>Important: HiLink/Ethernet Modems vs. Stick Modems</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="prose prose-sm max-w-none">
                <p>There are two main types of USB modems, and they behave very differently. Understanding which type you have is key to knowing which features are available to you.</p>
                <h4>Stick Mode (Full Feature Support)</h4>
                <ul className="list-disc pl-5">
                  <li><strong>How it works:</strong> The modem presents itself as a traditional serial device (like `ppp0` or `wwan0`). The operating system (via `ModemManager`) is responsible for establishing and managing the connection.</li>
                  <li><strong>Feature Support:</strong>
                    <ul className='list-disc pl-5'>
                      <li>✅ Proxy Creation & Control</li>
                      <li>✅ **IP Rotation (Manual & Automatic)**</li>
                      <li>✅ **Modem Control (Send/Read SMS, USSD Commands)**</li>
                    </ul>
                  </li>
                  <li><strong>How to identify:</strong> These modems are explicitly detected by `mmcli` and will have `mmcli_enhanced` as their source on the Modem Status page. Rotation and Control features will be enabled for them.</li>
                </ul>
                <h4>HiLink / RNDIS Mode (Partial Feature Support)</h4>
                 <ul className="list-disc pl-5">
                  <li><strong>How it works:</strong> The modem acts like a mini-router or USB Ethernet adapter. It manages the cellular connection internally and provides a simple network connection to your server (like `enx...` or `usb...`). Your server gets an IP address from the modem itself (e.g., 192.168.8.100).</li>
                  <li><strong>Feature Support:</strong>
                     <ul className='list-disc pl-5'>
                        <li>✅ Proxy Creation & Control</li>
                        <li>❌ **IP Rotation is NOT supported.** The application has no standard way to tell this type of modem to get a new IP address.</li>
                        <li>❌ **Modem Control (SMS/USSD) is NOT supported.** The cellular functions are hidden behind the modem's internal router.</li>
                    </ul>
                  </li>
                   <li><strong>How to identify:</strong> These modems are detected as standard network interfaces. On the IP Rotation and Modem Control pages, you will see messages indicating that the features are unavailable for this modem type.</li>
                </ul>
              </AccordionContent>
            </AccordionItem>
            <AccordionItem value="item-1">
              <AccordionTrigger>
                <div className="flex items-center gap-2">
                  <Wifi className="h-5 w-5 text-blue-500" />
                  <span>How does Modem Detection work?</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="prose prose-sm max-w-none">
                <p>Proxy Pilot uses a hybrid detection method:</p>
                <ul className="list-disc pl-5">
                  <li><strong>Primary Method (ip addr):</strong> The application first uses the standard Linux `ip addr` command to find network interfaces that look like USB modems (e.g., `enx...`, `usb...`, `ppp...`). This method is fast and works for all modem types, including HiLink.</li>
                  <li><strong>Enhancement (ModemManager):</strong> If `ModemManager` is installed and running, the application will then use `mmcli` to get more detailed information for "Stick Mode" modems, such as their real name (e.g., "Huawei E3372") and device ID. This enhancement is crucial for advanced features like IP Rotation and SMS/USSD control.</li>
                </ul>
              </AccordionContent>
            </AccordionItem>
            
            <AccordionItem value="item-2">
              <AccordionTrigger>
                <div className="flex items-center gap-2">
                  <Network className="h-5 w-5 text-green-500" />
                  <span>Understanding Proxy Control & Authentication</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="prose prose-sm max-w-none">
                <p>The "Proxy Control" page is where you manage individual proxy servers for each modem.</p>
                <ul className="list-disc pl-5">
                  <li><strong>Starting/Stopping:</strong> A proxy server can only be started if its corresponding modem is in a 'connected' state.</li>
                  <li><strong>Authentication:</strong> You have full control over proxy credentials.
                    <ul className="list-disc pl-5">
                        <li><strong>Authenticated Mode:</strong> Use the "Edit" button to set a username and password. The proxy will restart and require these credentials.</li>
                        <li><strong>Open Mode:</strong> If you leave the username and password fields blank, the proxy will run in 'Open' mode. It will not require any authentication but will only be accessible from the server itself (it binds to the modem's specific IP, not 0.0.0.0).</li>
                    </ul>
                  </li>
                   <li><strong>Proxy List Page:</strong> This page shows all proxies that are currently 'running'. It will display the full credentials string for authenticated proxies and just `IP:Port` for open proxies.</li>
                </ul>
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="item-3">
              <AccordionTrigger>
                <div className="flex items-center gap-2">
                  <RotateCcw className="h-5 w-5 text-orange-500" />
                  <span>Why is IP Rotation disabled for my modem?</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="prose prose-sm max-w-none">
                <p>IP Rotation is a powerful feature, but it has a specific requirement: **the modem must be a "Stick Mode" device managed by ModemManager (`mmcli`).**</p>
                <p>
                  Modems that act like Ethernet adapters (HiLink mode, with interfaces like `enx...`) handle their connections internally. The operating system has no standard way to command them to disconnect and reconnect to get a new IP address. `ModemManager` provides this necessary control layer for compatible stick modems.
                </p>
                <p><strong>To enable IP Rotation:</strong></p>
                 <ul className="list-disc pl-5">
                  <li>Ensure `modemmanager` is installed on your server (`sudo apt install modemmanager`).</li>
                  <li>Use a "Stick Mode" modem that is recognized by `mmcli`. You can check this by running `mmcli -L` in your server's terminal.</li>
                  <li>On the "IP Rotation" page, the "Rotate" buttons will be automatically enabled for any modem detected via this enhanced method.</li>
                </ul>
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="item-4">
              <AccordionTrigger>
                <div className="flex items-center gap-2">
                  <Smartphone className="h-5 w-5 text-cyan-500" />
                  <span>Why can't I use Modem Control (SMS/USSD)?</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="prose prose-sm max-w-none">
                <p>Just like IP Rotation, the ability to send SMS and USSD commands relies entirely on **ModemManager (`mmcli`)** and a compatible "Stick Mode" modem. This is because `mmcli` provides the specific commands (`--messaging-create-sms`, `--3gpp-ussd-initiate`) to interact with the modem's cellular functions.</p>
                <p>If you are using a HiLink/Ethernet modem, these cellular functions are not exposed to the operating system, so this feature will be disabled.</p>
              </AccordionContent>
            </AccordionItem>
             <AccordionItem value="item-5">
              <AccordionTrigger>
                <div className="flex items-center gap-2">
                  <AlertCircle className="h-5 w-5 text-red-500" />
                  <span>Troubleshooting: "Unit 3proxy@...service not found" Error</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="prose prose-sm max-w-none">
                <p>This is the most common installation error. It means the system service template we created for 3proxy was not properly registered.</p>
                <p><strong>How to fix:</strong></p>
                <ol className="list-decimal pl-5">
                    <li>SSH into your server.</li>
                    <li>Ensure the file `/etc/systemd/system/3proxy@.service` exists and its content is correct.</li>
                    <li>Run the most important command: `sudo systemctl daemon-reload`. This tells the system to re-read all service files.</li>
                    <li><strong>Verify the fix</strong> by running `systemctl status 3proxy@.service`. You should see output saying the service is `disabled`. This is normal and correct! It means the system now recognizes the template. If you see `Unit 3proxy@.service not found`, there is still a problem with the file's name or location.</li>
                </ol>
                <p>After successful verification, restart the Proxy Pilot application, and the error should be gone.</p>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </CardContent>
      </Card>
    </>
  );
}
