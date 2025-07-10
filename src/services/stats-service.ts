'use server';

import { PythonShell } from 'python-shell';
import path from 'path';

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

export interface VnstatData {
    name: string;
    totalrx: number;
    totaltx: number;
    day: { rx: number; tx: number; date: { year: number, month: number, day: number } }[];
    month: { rx: number; tx: number; date: { year: number, month: number } }[];
    hour: { rx: number; tx: number; date: { year: number, month: number, day: number, hour: number } }[];
}


/**
 * Fetches a list of network interfaces monitored by vnstat.
 * @returns A promise that resolves to an array of interface names.
 */
export async function getNetworkInterfaces(): Promise<string[]> {
    return await runPythonScript(['get_vnstat_interfaces']);
}


/**
 * Fetches daily, monthly, and hourly stats for a specific interface.
 * @param interfaceName The name of the network interface.
 * @returns A promise that resolves to the comprehensive stats data.
 */
export async function getStatsForInterface(interfaceName: string): Promise<VnstatData> {
    return await runPythonScript(['get_vnstat_stats', interfaceName]);
}
