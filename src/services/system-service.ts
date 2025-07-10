
'use server';

import { PythonShell } from 'python-shell';
import path from 'path';

// This helper function runs the Python script and returns the parsed JSON output.
async function runPythonScript(args: string[]): Promise<any> {
  const options = {
    mode: 'text' as const,
    pythonPath: 'python3', // Assumes python3 is in the system's PATH
    scriptPath: path.join(process.cwd(), 'src', 'services'),
    args: args,
  };

  try {
    const results = await PythonShell.run('backend_controller.py', options);
    const result = JSON.parse(results[0]);
    if (!result.success) {
      throw new Error(result.error || 'The Python script reported an unkown execution error.');
    }
    return result.data; // Return the 'data' part of the result
  } catch (error) {
    console.error('PythonShell Error:', error);
    if (error instanceof Error) {
        throw new Error(`Backend script failed: ${error.message}`);
    }
    throw new Error('An unknown error occurred while executing the backend script.');
  }
}

export interface LogEntry {
    timestamp: string;
    level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG';
    message: string;
}

/**
 * Fetches the latest system logs from the backend.
 * @returns A promise that resolves to an array of log entries.
 */
export async function getSystemLogs(): Promise<LogEntry[]> {
    return await runPythonScript(['get_logs']);
}
