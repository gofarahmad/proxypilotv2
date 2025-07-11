
# src/services/backend_controller.py
import sys
import json
import subprocess
import os
from pathlib import Path
import shutil
import datetime
import re
import signal
import secrets

# --- Configuration ---
STATE_DIR = Path(os.path.expanduser("~")) / ".proxy_pilot_state"
STATE_DIR.mkdir(exist_ok=True)
PROXY_CONFIGS_FILE = STATE_DIR / "proxy_configs.json"
TUNNEL_PIDS_FILE = STATE_DIR / "tunnel_pids.json"
LOG_FILE = STATE_DIR / "activity.log"
LOG_MAX_ENTRIES = 200
THREPROXY_CONFIG_DIR = Path("/etc/3proxy/conf")
PORT_RANGE_START = 7001
PORT_RANGE_END = 8000

# --- Logging Helper ---
def log_message(level, message):
    """
    Writes a structured log entry to the application's log file.

    Args:
        level (str): The log level (e.g., 'INFO', 'ERROR', 'DEBUG').
        message (str): The log message.
    """
    try:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log_entry = json.dumps({"timestamp": timestamp, "level": level, "message": message})
        lines = []
        if LOG_FILE.exists():
            with open(LOG_FILE, 'r') as f:
                lines = f.readlines()
        while len(lines) >= LOG_MAX_ENTRIES:
            lines.pop(0)
        lines.append(log_entry + '\n')
        with open(LOG_FILE, 'w') as f:
            f.writelines(lines)
    except IOError as e:
        sys.stderr.write(f"Logging failed due to I/O error: {e}\n")
    except Exception as e:
        sys.stderr.write(f"An unexpected logging error occurred: {e}\n")

# --- Helper Functions ---
def run_command(command_list, timeout=15):
    """
    Executes a system command securely and captures its output.
    Uses 'pkexec' for commands requiring elevated privileges.

    Args:
        command_list (list): The command and its arguments as a list of strings.
        timeout (int): The command timeout in seconds.

    Returns:
        str: The stripped stdout from the command.

    Raises:
        Exception: If the command fails, times out, or is not found.
    """
    try:
        privileged_commands = ['systemctl', 'mmcli', 'cloudflared']
        cmd_to_check = command_list[0]
        
        if cmd_to_check == 'pkexec' and len(command_list) > 1:
            cmd_to_check = command_list[1]

        if cmd_to_check in privileged_commands and command_list[0] != 'pkexec':
             command_list.insert(0, 'pkexec')

        result = subprocess.run(
            command_list, check=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except FileNotFoundError:
        cmd = command_list[1] if command_list[0] == 'pkexec' else command_list[0]
        error_msg = f"Command not found: '{cmd}'. Is it installed and in the system's PATH?"
        log_message("ERROR", error_msg)
        raise Exception(error_msg)
    except subprocess.TimeoutExpired:
        error_msg = f"Command timed out: {' '.join(command_list)}"
        log_message("ERROR", error_msg)
        raise Exception(error_msg)
    except subprocess.CalledProcessError as e:
        error_output = e.stderr.strip() if e.stderr else "No error output."
        log_message("ERROR", f"Command failed: {' '.join(command_list)}. Stderr: {error_output}")
        if "couldn't find bearer" in error_output.lower():
            return json.dumps({"bearer_error": True, "message": error_output})
        if "unable to read database" in error_output.lower():
             return json.dumps({"vnstat_error": "not_ready", "message": error_output})
        if "Unit 3proxy@" in error_output and "not found" in error_output:
            raise Exception(f"Systemd unit file '3proxy@.service' not found. Please check installation steps. Error: {error_output}")
        raise Exception(f"Command failed: {' '.join(command_list)}\nError: {error_output}")

def run_and_parse_json(command_list, timeout=15):
    """Runs a command and parses its JSON output."""
    raw_output = run_command(command_list, timeout)
    if not raw_output:
        return {}
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        # Check for special error cases returned as JSON strings
        if isinstance(raw_output, str):
            try:
                data = json.loads(raw_output)
                if data.get("bearer_error") or data.get("vnstat_error"):
                    return data
            except json.JSONDecodeError:
                pass # Not a special case, fall through to the main error
        error_msg = f"Failed to parse JSON from command: {' '.join(command_list)}"
        log_message("ERROR", error_msg)
        raise Exception(f"{error_msg}\nRaw Output: {raw_output}")

def read_state_file(file_path, default_value={}):
    """Reads and parses a JSON state file, returning a default value on failure."""
    if not file_path.exists():
        return default_value
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        log_message("ERROR", f"Could not read or parse state file: {file_path}. Returning default.")
        return default_value

def write_state_file(file_path, data):
    """Writes data to a JSON state file."""
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
    except IOError as e:
        log_message("ERROR", f"Could not write to state file {file_path}: {e}")
        raise

def get_or_create_proxy_config(interface_name, all_configs):
    """Gets an existing proxy config or generates a new one with unique ports and credentials."""
    if interface_name in all_configs and 'httpPort' in all_configs[interface_name] and 'socksPort' in all_configs[interface_name]:
        return all_configs[interface_name], False
    
    used_ports = set()
    for config in all_configs.values():
        if 'httpPort' in config: used_ports.add(config['httpPort'])
        if 'socksPort' in config: used_ports.add(config['socksPort'])

    new_http_port = PORT_RANGE_START
    while new_http_port in used_ports or (new_http_port + (PORT_RANGE_END - PORT_RANGE_START) + 1) in used_ports:
        new_http_port += 1
        if new_http_port > PORT_RANGE_END:
            raise Exception("No available ports in the specified range.")

    new_socks_port = new_http_port + (PORT_RANGE_END - PORT_RANGE_START)
    
    new_username = f"user_{secrets.token_hex(2)}"
    new_password = secrets.token_hex(8)

    new_config = {
        "httpPort": new_http_port, 
        "socksPort": new_socks_port,
        "username": new_username, 
        "password": new_password, 
        "bindIp": "0.0.0.0", 
        "customName": None
    }
    log_message("INFO", f"Generated new proxy config for {interface_name} on HTTP:{new_http_port}/SOCKS:{new_socks_port} with user '{new_username}'.")
    return new_config, True

def generate_3proxy_config_content(config, egress_ip):
    """Generates the content for a 3proxy configuration file."""
    if not egress_ip or not config.get('httpPort') or not config.get('socksPort'):
        return None

    username = config.get('username')
    password = config.get('password')
    is_authenticated = username and password

    lines = [
        "daemon",
        "nserver 8.8.8.8",
        "nserver 8.8.4.4",
        "nscache 65536",
        "timeouts 1 5 30 60 180 1800 15 60",
    ]

    if is_authenticated:
        lines.extend([
            f"users {username}:CL:{password}",
            "auth strong",
            f"allow {username}"
        ])
        lines.append(f"proxy -p{config['httpPort']} -i0.0.0.0 -e{egress_ip}")
        lines.append(f"socks -p{config['socksPort']} -i0.0.0.0 -e{egress_ip}")
    else:
        lines.append("auth none")
        lines.append(f"proxy -a -p{config['httpPort']} -i0.0.0.0 -e{egress_ip}")
        lines.append(f"socks -a -p{config['socksPort']} -i0.0.0.0 -e{egress_ip}")
    
    lines.append("flush")
    return "\n".join(lines)


def write_3proxy_config_file(interface_name, egress_ip):
    """Writes a 3proxy configuration file for a given modem interface."""
    try:
        THREPROXY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        all_configs = read_state_file(PROXY_CONFIGS_FILE)
        interface_config = all_configs.get(interface_name)
        if not interface_config:
            raise Exception(f"No configuration found for {interface_name}")
        
        config_content = generate_3proxy_config_content(interface_config, egress_ip)
        if not config_content:
            log_message("WARN", f"Could not generate config for {interface_name} (missing IP?). Skipping write.")
            return None

        config_file_path = THREPROXY_CONFIG_DIR / f"{interface_name}.cfg"
        with open(config_file_path, 'w') as f:
            f.write(config_content)
        log_message("DEBUG", f"Wrote 3proxy config for {interface_name}.")
        return str(config_file_path)
    except Exception as e:
        log_message("ERROR", f"Failed to write 3proxy config for {interface_name}: {e}")
        raise

# --- Core Logic Functions ---
def is_command_available(command):
    """Checks if a command is available in the system's PATH."""
    return shutil.which(command) is not None

def get_proxy_status(interface_name, modem_status):
    """Checks if the 3proxy service for a given interface is active."""
    if modem_status != 'connected':
        return 'stopped'
    try:
        run_command(['systemctl', 'is-active', '--quiet', f"3proxy@{interface_name}.service"])
        return 'running'
    except Exception:
        # This is expected if the service is not running. Not an error.
        return 'stopped'
        
def get_public_ip(interface_name):
    """Fetches the public IP address for a given network interface."""
    if not is_command_available("curl"):
        log_message("WARN", "curl not installed. Cannot fetch public IPs.")
        return None
    try:
        return run_command(['curl', '--interface', interface_name, '--connect-timeout', '5', 'https://api.ipify.org'], timeout=10)
    except Exception:
        log_message("WARN", f"Could not fetch public IP for {interface_name}. It may not be fully online.")
        return None

def get_primary_lan_ip():
    """Finds the primary non-modem IPv4 address of the server."""
    try:
        interfaces = run_and_parse_json(['ip', '-j', 'addr'])
        modem_pattern = re.compile(r'^(enx|usb|wwan|ppp)')
        excluded_pattern = re.compile(r'^(lo|docker|veth|br-|cali|vxlan)')
        
        for iface in interfaces:
            ifname = iface.get('ifname', '')
            if not excluded_pattern.match(ifname) and not modem_pattern.match(ifname):
                for addr_info in iface.get('addr_info', []):
                    if addr_info.get('family') == 'inet':
                        return addr_info.get('local')
        log_message("WARN", "Could not determine primary LAN IP. No suitable interface found.")
        return None
    except Exception as e:
        log_message("ERROR", f"Could not determine primary LAN IP: {e}")
        return None


def get_modems_from_ip_addr():
    """Gets a base list of modem-like interfaces using the 'ip' command."""
    modems = {}
    if not is_command_available("ip"):
        log_message("ERROR", "`ip` command not found. Cannot perform primary modem detection.")
        return modems

    try:
        interfaces = run_and_parse_json(['ip', '-j', 'addr'])
        modem_interface_pattern = re.compile(r'^(enx|usb|wwan|ppp)')
        server_lan_ip = get_primary_lan_ip()

        for iface in interfaces:
            ifname = iface.get('ifname', '')
            if modem_interface_pattern.match(ifname):
                ip_address = next((addr.get('local') for addr in iface.get('addr_info', []) if addr.get('family') == 'inet'), None)
                is_connected = iface.get('operstate') == 'UP' and ip_address
                status = 'connected' if is_connected else 'disconnected'
                
                modems[ifname] = {
                    "id": iface.get('address', ifname),
                    "name": f"Modem ({ifname})",
                    "interfaceName": ifname,
                    "status": status,
                    "ipAddress": ip_address,
                    "source": "ip_addr",
                    "serverLanIp": server_lan_ip,
                }
    except Exception as e:
        log_message("ERROR", f"Error detecting modems from 'ip addr': {e}")
    return modems

def enhance_with_mmcli_data(modems_dict):
    """Enhances modem data with details from ModemManager (mmcli)."""
    if not is_command_available("mmcli"):
        log_message("INFO", "`mmcli` not found. Skipping enhanced modem detection.")
        return modems_dict

    try:
        modem_list_data = run_and_parse_json(['mmcli', '-L', '-J'])
        for modem_path in modem_list_data.get('modem-list', []):
            try:
                details = run_and_parse_json(['mmcli', '-m', modem_path, '-J'])
                ifname = details.get('modem', {}).get('generic', {}).get('primary-port')
                if ifname and ifname in modems_dict:
                    device_id = details.get('modem', {}).get('generic', {}).get('device-identifier', ifname)
                    vendor = details.get('device-properties', {}).get('device.vendor.name', '')
                    model = details.get('device-properties', {}).get('device.model', f'Modem ({device_id[-6:]})')
                    modems_dict[ifname]['id'] = device_id
                    modems_dict[ifname]['name'] = f"{vendor} {model}".strip() if (vendor or model) else f"Modem ({ifname})"
                    modems_dict[ifname]['source'] = "mmcli_enhanced"
            except Exception as e:
                log_message("WARN", f"Could not get details for modem {modem_path}. It might be initializing. Error: {e}")
                continue
    except Exception as e:
        log_message("ERROR", f"Failed to enhance modem data with mmcli: {e}")
    return modems_dict

def get_all_modem_statuses():
    """
    Retrieves the status of all detected modems, their IPs, and proxy status.
    This is the main data-gathering function for the application.
    """
    try:
        all_modems = get_modems_from_ip_addr()
        all_modems = enhance_with_mmcli_data(all_modems)
        
        status_list = list(all_modems.values())
        if not status_list:
            log_message("INFO", "No modems detected by any method.")
            return {"success": True, "data": []}

        proxy_configs = read_state_file(PROXY_CONFIGS_FILE)
        configs_changed = False

        for modem in status_list:
            iface_name = modem['interfaceName']
            
            # Get or create config, and update the master config dict if new
            modem_cfg, created = get_or_create_proxy_config(iface_name, proxy_configs)
            if created:
                proxy_configs[iface_name] = modem_cfg
                configs_changed = True
            
            modem['proxyConfig'] = modem_cfg
            if modem_cfg.get('customName'):
                 modem['name'] = modem_cfg['customName']

            # Fetch public IP and get proxy status only if connected
            if modem['status'] == 'connected':
                modem['publicIpAddress'] = get_public_ip(iface_name)
                modem['proxyStatus'] = get_proxy_status(iface_name, modem['status'])
                # Always ensure config file is up-to-date with the latest IP
                if modem['ipAddress']:
                    write_3proxy_config_file(iface_name, modem['ipAddress'])
            else:
                modem['publicIpAddress'] = None
                modem['proxyStatus'] = 'stopped'

        if configs_changed:
            write_state_file(PROXY_CONFIGS_FILE, proxy_configs)

        return {"success": True, "data": status_list}
    except Exception as e:
        log_message("ERROR", f"Critical error in get_all_modem_statuses: {e}")
        return {"success": False, "error": str(e)}

def proxy_action(action, interface_name):
    """Starts, stops, or restarts a proxy service for a given interface."""
    try:
        log_message("INFO", f"Requesting to {action} proxy for {interface_name}.")
        # Pre-flight check to create config if it's missing on a start/restart
        if action in ['start', 'restart']:
            config_file_path = THREPROXY_CONFIG_DIR / f"{interface_name}.cfg"
            if not config_file_path.exists():
                log_message("WARN", f"Proxy config for {interface_name} not found. Attempting to create it.")
                statuses_res = get_all_modem_statuses()
                if not statuses_res['success']: raise Exception("Could not get modem statuses to create fallback config.")
                modem = next((m for m in statuses_res['data'] if m['interfaceName'] == interface_name), None)
                if not modem or not modem['ipAddress']:
                     raise Exception(f"Modem {interface_name} not connected or has no IP. Cannot {action} proxy.")
                write_3proxy_config_file(interface_name, modem['ipAddress'])

        service_name = f"3proxy@{interface_name}.service"
        run_command(['systemctl', action, service_name])
        log_message("INFO", f"Proxy action '{action}' successful for {interface_name}.")
        return {"success": True, "data": {"message": f"Proxy {action} successful."}}
    except Exception as e:
        log_message("ERROR", f"Proxy action '{action}' for {interface_name} failed: {e}")
        return {"success": False, "error": str(e)}

def modem_action(action, interface_name, args_json):
    """Handles modem-specific actions like sending SMS or USSD commands via mmcli."""
    try:
        args = json.loads(args_json)
        log_message("INFO", f"Performing modem action '{action}' for {interface_name}.")
        if not is_command_available("mmcli"):
            raise Exception("`mmcli` is required for this feature.")

        modems_data = run_and_parse_json(['mmcli', '-L', '-J'])
        modem_path = next((m for m in modems_data.get('modem-list', []) if run_and_parse_json(['mmcli', '-m', m, '-J']).get('modem', {}).get('generic', {}).get('primary-port') == interface_name), None)
        
        if not modem_path:
            raise Exception(f"Could not find modem '{interface_name}' managed by ModemManager.")

        if action == 'send-sms':
            sms_path = run_and_parse_json(['mmcli', '-m', modem_path, f'--messaging-create-sms=text="{args["message"]}",number="{args["recipient"]}"', '-J']).get('sms', {}).get('path')
            if not sms_path: raise Exception("Failed to create SMS in modem.")
            run_command(['mmcli', '-s', sms_path, '--send'])
            run_command(['mmcli', '-m', modem_path, f'--messaging-delete-sms={sms_path.split("/")[-1]}'])
            return {"success": True, "data": {"message": "SMS sent successfully."}}
        
        elif action == 'read-sms':
            sms_list = run_and_parse_json(['mmcli', '-m', modem_path, '--messaging-list-sms', '-J']).get('modem', {}).get('messaging', {}).get('sms', [])
            messages = [run_and_parse_json(['mmcli', '-s', p, '-J']).get('sms', {}) for p in sms_list]
            formatted_messages = [{"id": sms.get('path', '').split('/')[-1], "from": sms.get('content', {}).get('number', 'Unknown'), "timestamp": sms.get('properties', {}).get('timestamp', ''), "content": sms.get('content', {}).get('text', '')} for sms in messages]
            return {"success": True, "data": formatted_messages}

        elif action == 'send-ussd':
            response = run_command(['mmcli', '-m', modem_path, f'--3gpp-ussd-initiate={args["ussdCode"]}'])
            return {"success": True, "data": {"response": response}}

        return {"success": False, "error": f"Unknown modem action: {action}"}
    except Exception as e:
        log_message("ERROR", f"Modem action '{action}' for {interface_name} failed: {e}")
        return {"success": False, "error": str(e)}

def rotate_ip(interface_name):
    """
    Performs an IP rotation for a modem by disconnecting and reconnecting its data bearer.
    This function specifically requires the modem to be managed by ModemManager.
    """
    try:
        log_message("INFO", f"Starting IP rotation for {interface_name}.")
        if not is_command_available("mmcli"):
            raise Exception("`mmcli` is required for IP rotation.")

        statuses_res = get_all_modem_statuses()
        if not statuses_res.get("success"): raise Exception("Failed to get modem status before rotation.")
        
        modem = next((m for m in statuses_res['data'] if m['interfaceName'] == interface_name), None)
        if not modem or 'mmcli' not in modem.get('source', ''):
            raise Exception(f"IP rotation only supported for ModemManager-controlled modems. {interface_name} is not.")
        
        modem_mm_path = run_and_parse_json(['mmcli', '-m', modem['id'], '-J']).get('modem',{}).get('generic',{}).get('device')
        if not modem_mm_path:
            modems_list = run_and_parse_json(['mmcli', '-L', '-J']).get('modem-list', [])
            modem_mm_path = next((p for p in modems_list if run_and_parse_json(['mmcli', '-m', p, '-J']).get('modem',{}).get('generic',{}).get('primary-port') == interface_name), None)
            if not modem_mm_path:
                raise Exception(f"Could not find mmcli path for modem {interface_name}")

        log_message("DEBUG", f"[{interface_name}] Found mmcli path: {modem_mm_path}")
        
        details = run_and_parse_json(['mmcli', '-m', modem_mm_path, '-J'], timeout=30)
        if details.get("bearer_error"): raise Exception(f"Could not get modem details for rotation: {details.get('message')}")
        
        active_bearer = next((b for b in details.get('modem',{}).get('bearers',[]) if run_and_parse_json(['mmcli','-b',b,'-J']).get('bearer',{}).get('status',{}).get('connected')), None)

        if active_bearer:
            log_message("INFO", f"[{interface_name}] Disconnecting active bearer {active_bearer}...")
            run_command(['mmcli', '-b', active_bearer, '--disconnect'], timeout=30)
        else:
            log_message("WARN", f"[{interface_name}] No active bearer found. Proceeding to connect.")

        run_command(['sleep', '10']) # Wait for network deregistration

        apn = details.get('modem',{}).get('3gpp',{}).get('operator-code', '')
        log_message("INFO", f"[{interface_name}] Creating new bearer (APN: {apn or 'none'})...")
        new_bearer = run_and_parse_json(['mmcli','-m',modem_mm_path,f'--create-bearer={"apn="+apn if apn else ""}'], timeout=45).get('bearer',{}).get('path')
        if not new_bearer: raise Exception(f"Failed to create new bearer for {interface_name}.")
        
        log_message("INFO", f"[{interface_name}] Connecting new bearer {new_bearer}...")
        run_command(['mmcli', '-b', new_bearer, '--connect'], timeout=60)
        
        run_command(['sleep', '15']) # Wait for IP assignment
        
        log_message("INFO", f"[{interface_name}] Restarting proxy to bind to new IP.")
        proxy_action('restart', interface_name)

        final_ip = get_public_ip(interface_name) or "unknown"
        log_message("INFO", f"IP rotation for {interface_name} complete. New IP: {final_ip}.")
        return {"success": True, "data": {"message": f"IP rotated successfully. New IP: {final_ip}", "newIp": final_ip}}

    except Exception as e:
        log_message("ERROR", f"IP rotation for {interface_name} failed: {e}")
        return {"success": False, "error": str(e)}

# --- Tunnel Management ---
def get_tunnel_pids(): return read_state_file(TUNNEL_PIDS_FILE)
def save_tunnel_pids(pids): write_state_file(TUNNEL_PIDS_FILE, pids)
def is_pid_running(pid):
    if not pid: return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def start_tunnel(tunnel_id, local_port, linked_to, tunnel_type, cloudflare_id=None):
    pids = get_tunnel_pids()
    if tunnel_id in pids and is_pid_running(pids[tunnel_id].get('pid')):
        return {"success": True, "message": "Tunnel already running."}
    
    if tunnel_type == "Ngrok":
        if not is_command_available("ngrok"): raise Exception("`ngrok` command not found.")
        proc = subprocess.Popen(['ngrok', 'tcp', str(local_port), '--log=stdout'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, preexec_fn=os.setsid)
        run_command(['sleep', '2'])
        try:
            tunnels_api = run_and_parse_json(['curl', '-s', 'http://127.0.0.1:4040/api/tunnels'])
            tunnel_info = next((t for t in tunnels_api.get('tunnels', []) if t.get('proto') == 'tcp' and str(t.get('config', {}).get('addr')).endswith(str(local_port))), None)
            if not tunnel_info:
                proc.terminate()
                raise Exception("Could not find started ngrok tunnel in API.")
            url = tunnel_info.get('public_url')
        except Exception as e:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            raise e
    elif tunnel_type == "Cloudflare":
        if not is_command_available("cloudflared"): raise Exception("`cloudflared` command not found.")
        if not cloudflare_id: raise Exception("Cloudflare Tunnel ID is required.")
        url = f"tcp://{cloudflare_id}.trycloudflare.com" # Predicted URL
        proc = subprocess.Popen(['cloudflared', 'tunnel', 'run', '--url', f'tcp://localhost:{local_port}', cloudflare_id], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, preexec_fn=os.setsid)
        run_command(['sleep', '2'])
    else:
        raise Exception(f"Unknown tunnel type: {tunnel_type}")

    pids[tunnel_id] = {"pid": proc.pid, "port": local_port, "url": url, "type": tunnel_type, "linkedTo": linked_to}
    save_tunnel_pids(pids)
    log_message("INFO", f"Started {tunnel_type} tunnel '{tunnel_id}' on port {local_port} with PID {proc.pid}.")
    return {"success": True, "data": pids[tunnel_id]}

def stop_tunnel(tunnel_id):
    pids = get_tunnel_pids()
    info = pids.get(tunnel_id)
    if not info or not is_pid_running(info.get('pid')):
        if tunnel_id in pids: del pids[tunnel_id]; save_tunnel_pids(pids)
        return {"success": True, "message": "Tunnel was not running."}
    try:
        os.killpg(os.getpgid(info['pid']), signal.SIGTERM)
        log_message("INFO", f"Stopped tunnel '{tunnel_id}' (PID: {info['pid']}).")
    except OSError as e:
        log_message("WARN", f"Could not kill process group for tunnel '{tunnel_id}': {e}.")
    del pids[tunnel_id]
    save_tunnel_pids(pids)
    return {"success": True, "message": "Tunnel stopped."}

def get_all_tunnel_statuses():
    pids = get_tunnel_pids()
    statuses = []
    pids_changed = False
    for tid, info in list(pids.items()):
        if is_pid_running(info.get('pid')):
            statuses.append({"id": tid, "type": info.get("type"), "status": "active", "url": info.get("url"), "localPort": info.get("port"), "linkedTo": info.get("linkedTo")})
        else:
            del pids[tid]
            pids_changed = True
    if pids_changed: save_tunnel_pids(pids)
    return {"success": True, "data": statuses}

def get_available_cloudflare_tunnels():
    if not is_command_available("cloudflared"): return {"success": True, "data": []}
    cf_dir = Path(os.path.expanduser("~")) / ".cloudflared"
    tunnels = []
    if cf_dir.exists():
        for cert_file in cf_dir.glob("*.pem"):
            if '-' in cert_file.stem: # Basic validation for UUID format
                tunnels.append({"id": cert_file.stem, "name": f"Cloudflare Tunnel ({cert_file.stem[:8]}...)"})
    return {"success": True, "data": tunnels}

# --- vnstat Functions ---
def get_vnstat_interfaces():
    if not is_command_available("vnstat"): raise Exception("`vnstat` is not installed.")
    try:
        vnstat_output = run_and_parse_json(['vnstat', '-J'])
        vnstat_interfaces = {iface.get('name') for iface in vnstat_output.get('interfaces', [])}
        
        # We only want to show stats for interfaces that are actual modems
        modem_interfaces = set(get_modem_interface_names())
        relevant_interfaces = sorted(list(vnstat_interfaces.intersection(modem_interfaces)))
        
        return {"success": True, "data": relevant_interfaces}
    except Exception as e:
        # This can happen if vnstat hasn't collected any data yet
        if "vnstat_error" in str(e):
             log_message("WARN", f"Vnstat database may not be ready: {e}")
             return {"success": True, "data": []}
        log_message("ERROR", f"Failed to get vnstat interface list: {e}")
        return {"success": False, "error": str(e)}

def get_modem_interface_names():
    """Helper to get a simple list of modem-like interface names."""
    try:
        interfaces = run_and_parse_json(['ip', '-j', 'addr'])
        modem_pattern = re.compile(r'^(enx|usb|wwan|ppp)')
        return [iface.get('ifname') for iface in interfaces if modem_pattern.match(iface.get('ifname', ''))]
    except Exception:
        return []

def get_vnstat_stats(interface_name):
    if not is_command_available("vnstat"): raise Exception("`vnstat` is not installed.")
    try:
        # -j gives more reliable complete data than -J for single interfaces
        data = run_and_parse_json(['vnstat', '-i', interface_name, '-j'])
        iface_data = data['interfaces'][0]
        stats = {
            "name": iface_data.get('name', interface_name),
            "totalrx": iface_data.get('traffic', {}).get('total', {}).get('rx', 0),
            "totaltx": iface_data.get('traffic', {}).get('total', {}).get('tx', 0),
            "day": iface_data.get('traffic', {}).get('day', []),
            "month": iface_data.get('traffic', {}).get('month', []),
            "hour": iface_data.get('traffic', {}).get('hour', [])
        }
        return {"success": True, "data": stats}
    except Exception as e:
        if "vnstat_error" in str(e) or "no data available" in str(e).lower():
             return {"success": False, "error": f"Vnstat has no data for {interface_name} yet."}
        log_message("ERROR", f"Failed to get vnstat stats for {interface_name}: {e}")
        return {"success": False, "error": str(e)}

# --- System & Config Functions ---
def get_logs():
    """Retrieves all log entries from the log file."""
    try:
        if not LOG_FILE.exists(): return {"success": True, "data": []}
        with open(LOG_FILE, 'r') as f: lines = f.readlines()
        log_entries = [json.loads(line.strip()) for line in lines if line.strip()]
        return {"success": True, "data": log_entries}
    except Exception as e:
        return {"success": False, "error": f"Failed to read log file: {e}"}

def get_all_configs():
    """Retrieves the entire proxy configurations state."""
    return {"success": True, "data": read_state_file(PROXY_CONFIGS_FILE)}

def update_proxy_config(interface_name, updates_json):
    """Updates the configuration for a specific proxy and restarts it if credentials change."""
    try:
        updates = json.loads(updates_json)
        all_configs = read_state_file(PROXY_CONFIGS_FILE)
        
        if interface_name not in all_configs: all_configs[interface_name] = {}
        all_configs[interface_name].update(updates)
        
        write_state_file(PROXY_CONFIGS_FILE, all_configs)
        log_message("INFO", f"Updated config for {interface_name} with: {updates}")
        
        if 'username' in updates or 'password' in updates:
            if get_proxy_status(interface_name, 'connected') == 'running':
                log_message("INFO", f"Credentials changed for running proxy {interface_name}. Restarting.")
                proxy_action('restart', interface_name)
        
        return {"success": True, "data": all_configs[interface_name]}
    except Exception as e:
        log_message("ERROR", f"Failed to update config for {interface_name}: {e}")
        return {"success": False, "error": str(e)}

# --- Main Execution Block ---
def main():
    """
    Main function to dispatch actions based on command-line arguments.
    """
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "No action specified."}))
        sys.exit(1)

    action = sys.argv[1]
    result = {}
    try:
        log_message("DEBUG", f"Backend action '{action}' called.")
        if action == 'get_all_modem_statuses':
            result = get_all_modem_statuses()
        elif action == 'rotate_ip':
            result = rotate_ip(sys.argv[2])
        elif action in ['start', 'stop', 'restart']:
            result = proxy_action(action, sys.argv[2])
        elif action in ['send-sms', 'read-sms', 'send-ussd']:
            result = modem_action(action, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else '{}')
        elif action == 'start_tunnel':
            tunnel_id, local_port, linked_to, tunnel_type = sys.argv[2:6]
            cloudflare_id = sys.argv[6] if len(sys.argv) > 6 else None
            result = start_tunnel(tunnel_id, int(local_port), linked_to, tunnel_type, cloudflare_id)
        elif action == 'stop_tunnel':
            result = stop_tunnel(sys.argv[2])
        elif action == 'get_all_tunnel_statuses':
            result = get_all_tunnel_statuses()
        elif action == 'get_available_cloudflare_tunnels':
            result = get_available_cloudflare_tunnels()
        elif action == 'get_vnstat_interfaces':
            result = get_vnstat_interfaces()
        elif action == 'get_vnstat_stats':
            result = get_vnstat_stats(sys.argv[2])
        elif action == 'get_logs':
            result = get_logs()
        elif action == 'get_all_configs':
            result = get_all_configs()
        elif action == 'update_proxy_config':
            result = update_proxy_config(sys.argv[2], sys.argv[3])
        else:
            result = {"success": False, "error": f"Unknown action: {action}"}
    except Exception as e:
        log_message("ERROR", f"An unexpected error occurred in main() for action '{action}': {e}")
        result = {"success": False, "error": str(e)}

    print(json.dumps(result))

if __name__ == "__main__":
    main()
