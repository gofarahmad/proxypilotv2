
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
    // Join all lines of output, in case the JSON is fragmented.
    const rawResult = results.join('');
    const result = JSON.parse(rawResult);
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

export async function rebindProxy(interfaceName: string, newIp: string): Promise<boolean> {
  console.log(`[Service] Rebinding proxy on ${interfaceName} to ${newIp}. Restarting service.`);
  await restartProxy(interfaceName);
  return true;
}

export async function startProxy(interfaceName: string): Promise<boolean> {
  await runPythonScript(['start', interfaceName]);
  return true;
}

export async function stopProxy(interfaceName: string): Promise<boolean> {
  await runPythonScript(['stop', interfaceName]);
  return true;
}

export async function restartProxy(interfaceName: string): Promise<boolean> {
  await runPythonScript(['restart', interfaceName]);
  return true;
}

export interface ProxyConfig {
    httpPort: number;
    socksPort: number;
    bindIp?: string;
    username?: string;
    password?: string;
    customName?: string | null;
}

export async function getProxyConfig(interfaceName: string): Promise<ProxyConfig | null> {
    const allConfigs = await runPythonScript(['get_all_configs']);
    return allConfigs[interfaceName] || null;
}

export async function getAllProxyConfigs(): Promise<Record<string, ProxyConfig>> {
    return await runPythonScript(['get_all_configs']);
}

export async function updateProxyCredentials(interfaceName: string, username?: string, password?: string): Promise<boolean> {
    const credentials = { username, password };
    await runPythonScript(['update_proxy_config', interfaceName, JSON.stringify(credentials)]);
    // The Python script will automatically restart the proxy after updating credentials
    return true;
}
