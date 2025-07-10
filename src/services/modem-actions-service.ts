
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
    // The result from Python is a JSON string in the first element of the array.
    const result = JSON.parse(results[0]); 
    if (!result.success) {
      // If the script reported an error, throw it so it can be caught by the caller.
      throw new Error(result.error || 'The Python script reported an unkown execution error.');
    }
    // On success, return the 'data' part of the result.
    return result.data; 
  } catch (error) {
    console.error('PythonShell Error:', error);
    // Re-throw the error to be handled by the calling server action.
    if (error instanceof Error) {
        throw new Error(`Backend script failed: ${error.message}`);
    }
    throw new Error('An unknown error occurred while executing the backend script.');
  }
}


export interface SmsMessage {
    id: string;
    from: string;
    timestamp: string;
    content: string;
}

/**
 * Sends an SMS message via a modem interface.
 * @param interfaceName The modem interface (e.g., 'ppp0').
 * @param recipient The phone number of the recipient.
 * @param message The content of the SMS.
 * @returns A promise that resolves to an object indicating success and a message.
 */
export async function sendSms(interfaceName: string, recipient: string, message: string): Promise<{ success: boolean; message: string }> {
    const args = { recipient, message };
    const data = await runPythonScript(['send-sms', interfaceName, JSON.stringify(args)]);
    return { success: true, message: data.message };
}

/**
 * Reads all SMS messages from a modem interface.
 * @param interfaceName The modem interface (e.g., 'ppp0').
 * @returns A promise that resolves to an array of SMS messages.
 */
export async function readSms(interfaceName: string): Promise<SmsMessage[]> {
    const data = await runPythonScript(['read-sms', interfaceName, '{}']);
    return data;
}

/**
 * Sends a USSD command via a modem interface.
 * @param interfaceName The modem interface (e.g., 'ppp0').
 * @param ussdCode The USSD code to send (e.g., '*123#').
 * @returns A promise that resolves to an object indicating success and the response message.
 */
export async function sendUssd(interfaceName: string, ussdCode: string): Promise<{ success: boolean; response: string }> {
    const args = { ussdCode };
    const data = await runPythonScript(['send-ussd', interfaceName, JSON.stringify(args)]);
    return { success: true, response: data.response };
}
