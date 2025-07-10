
'use server';

import { PythonShell } from 'python-shell';
import path from 'path';

// Helper function to run the Python backend script
async function runPythonScript(args: string[]): Promise<any> {
  const options = {
    mode: 'text' as const,
    pythonPath: 'python3',
    scriptPath: path.join(process.cwd(), 'src', 'services'),
    args: args,
  };

  try {
    const results = await PythonShell.run('backend_controller.py', options);
    const result = JSON.parse(results[0]);
    if (!result.success) {
      throw new Error(result.error || 'The Python script reported an unknown execution error.');
    }
    return result.data;
  } catch (error) {
    console.error('PythonShell Error:', error);
    if (error instanceof Error) {
      throw new Error(`Backend script failed: ${error.message}`);
    }
    throw new Error('An unknown error occurred while executing the backend script.');
  }
}


export interface TunnelStatus {
  id: string; // e.g., 'tunnel_ppp0'
  type: 'Ngrok' | 'Cloudflare';
  status: 'active' | 'inactive' | 'error';
  url: string | null;
  localPort: number; // The local proxy port it's connected to
  linkedTo: string | null; // Name of the modem/proxy it is linked to
}

export interface CloudflareTunnel {
  id: string; // The UUID of the tunnel
  name: string; // A display-friendly name
}

export async function getAvailableCloudflareTunnels(): Promise<CloudflareTunnel[]> {
  return await runPythonScript(['get_available_cloudflare_tunnels']);
}

/**
 * Retrieves the status of a single tunnel by its ID.
 * Note: This is less efficient than getting all statuses at once.
 * It's implemented by filtering the full list from the backend.
 * @param tunnelId The ID of the tunnel.
 * @returns A promise resolving to the tunnel's status or null if not found.
 */
export async function getTunnelStatus(tunnelId: string): Promise<TunnelStatus | null> {
  const allTunnels = await getAllTunnelStatuses();
  return allTunnels.find(t => t.id === tunnelId) || null;
}

/**
 * Fetches the statuses of all active tunnels from the backend.
 * @returns A promise resolving to an array of active tunnel statuses.
 */
export async function getAllTunnelStatuses(): Promise<TunnelStatus[]> {
    return await runPythonScript(['get_all_tunnel_statuses']);
}

/**
 * Starts a tunnel for a specific local port by calling the backend script.
 * @param tunnelId A unique identifier for the tunnel, e.g., `tunnel_ppp0`
 * @param localPort The local port the tunnel should expose.
 * @param linkedTo The name of the modem this tunnel is for.
 * @param tunnelType The provider to use ('Ngrok' or 'Cloudflare').
 * @param cloudflareId The ID of the Cloudflare tunnel (only for 'Cloudflare' type).
 * @returns A promise resolving to true if successful.
 */
export async function startTunnel(
  tunnelId: string, 
  localPort: number, 
  linkedTo: string, 
  tunnelType: 'Ngrok' | 'Cloudflare',
  cloudflareId?: string
): Promise<boolean> {
  const args = ['start_tunnel', tunnelId, String(localPort), linkedTo, tunnelType];
  if (tunnelType === 'Cloudflare' && cloudflareId) {
    args.push(cloudflareId);
  }
  await runPythonScript(args);
  return true;
}

/**
 * Stops a tunnel by calling the backend script.
 * @param tunnelId The ID of the tunnel to stop.
 * @returns A promise resolving to true if successful.
 */
export async function stopTunnel(tunnelId: string): Promise<boolean> {
  await runPythonScript(['stop_tunnel', tunnelId]);
  return true;
}

    