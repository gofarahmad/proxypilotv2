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
import fcntl  # Untuk file locking
import time
from typing import Dict, List, Tuple, Optional, Union, Any

# --- Configuration ---
CONFIG = {
    'STATE_DIR': Path(os.path.expanduser("~")) / ".proxy_pilot_state",
    'PROXY_CONFIGS_FILE': "proxy_configs.json",
    'TUNNEL_PIDS_FILE': "tunnel_pids.json",
    'LOG_FILE': "activity.log",
    'LOG_MAX_ENTRIES': 200,
    'THREPROXY_CONFIG_DIR': Path("/etc/3proxy/conf"),
    'HTTP_PORT_RANGE_START': 7001,
    'HTTP_PORT_RANGE_END': 8000,
    'SOCKS_PORT_RANGE_START': 8001,
    'SOCKS_PORT_RANGE_END': 9000,
    'DEFAULT_TIMEOUT': 15,
}

# --- Initialization ---
def initialize_environment():
    """Create necessary directories and resolve full file paths."""
    CONFIG['STATE_DIR'].mkdir(exist_ok=True)
    CONFIG['PROXY_CONFIGS_FILE'] = CONFIG['STATE_DIR'] / CONFIG['PROXY_CONFIGS_FILE']
    CONFIG['TUNNEL_PIDS_FILE'] = CONFIG['STATE_DIR'] / CONFIG['TUNNEL_PIDS_FILE']
    CONFIG['LOG_FILE'] = CONFIG['STATE_DIR'] / CONFIG['LOG_FILE']
    try:
        CONFIG['THREPROXY_CONFIG_DIR'].mkdir(parents=True, exist_ok=True)
    except PermissionError:
        sys.stderr.write(f"Permission denied: Could not create {CONFIG['THREPROXY_CONFIG_DIR']}. Please check permissions.\n")
        log_message("ERROR", f"Permission denied: Could not create {CONFIG['THREPROXY_CONFIG_DIR']}.")
        sys.exit(1)

# --- Logging Helper ---
def log_message(level: str, message: str) -> None:
    """Log a message with timestamp and level to the log file, with rotation."""
    try:
        log_file_path = CONFIG.get('LOG_FILE')
        if not isinstance(log_file_path, Path):
            log_file_path = Path(os.path.expanduser("~")) / ".proxy_pilot_state" / "activity.log"
            log_file_path.parent.mkdir(exist_ok=True)
        
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log_entry = json.dumps({"timestamp": timestamp, "level": level.upper(), "message": str(message)}) + '\n'

        with open(log_file_path, 'a+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                lines = f.readlines()
                
                if len(lines) >= CONFIG['LOG_MAX_ENTRIES']:
                    lines_to_keep = lines[-(CONFIG['LOG_MAX_ENTRIES'] - 1):]
                    f.seek(0)
                    f.truncate()
                    f.writelines(lines_to_keep)
                
                f.seek(0, os.SEEK_END)
                f.write(log_entry)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as e:
        sys.stderr.write(f"CRITICAL LOGGING FAILURE: {e}\n")

# --- State Management with File Locking ---
def read_state_file(file_path: Path, default_value: Any = None) -> Any:
    """Read a JSON state file safely with file locking."""
    if default_value is None:
        default_value = {}
    if not file_path.exists():
        return default_value
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, IOError, FileNotFoundError) as e:
        log_message("ERROR", f"Failed to read state file {file_path}: {e}")
        return default_value

def write_state_file(file_path: Path, data: Any) -> bool:
    """Write data to a JSON state file atomically and safely."""
    try:
        temp_file_path = file_path.with_suffix(f'.tmp{os.getpid()}')
        with open(temp_file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        
        os.replace(temp_file_path, file_path)
        return True
    except (IOError, TypeError) as e:
        log_message("ERROR", f"Failed to write state file {file_path}: {e}")
        return False

# --- Command Execution ---
def run_command(
    command_list: List[str], 
    timeout: Optional[int] = None, 
    check: bool = True,
    suppress_error: bool = False
) -> str:
    """
    Executes a system command and captures its output.
    Uses 'pkexec' for commands requiring root privileges.
    If suppress_error is True, it returns stderr instead of raising an exception.
    """
    if timeout is None:
        timeout = CONFIG['DEFAULT_TIMEOUT']

    privileged_commands = {'systemctl', 'mmcli', 'cloudflared', 'netfilter-persistent', 'iptables', 'kill'}
    cmd_to_check = command_list[0]
    
    if cmd_to_check in privileged_commands and 'pkexec' not in command_list:
        command_list.insert(0, 'pkexec')
        if timeout < 30: timeout = 30 
        
    try:
        result = subprocess.run(
            command_list,
            check=check,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='utf-8',
            errors='replace'
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
        
        if suppress_error:
            return error_output

        if "couldn't find bearer" in error_output.lower():
            return json.dumps({"bearer_error": True, "message": "Modem bearer (data connection) not found."})
        if "unable to read database" in error_output.lower():
            return json.dumps({"vnstat_error": "not_ready", "message": "vnstat database is not ready or has no data."})
        if "Unit 3proxy@" in error_output and "not found" in error_output:
            raise Exception("Systemd unit file '3proxy@.service' not found. Please check installation steps.")
        
        raise Exception(f"Command failed with exit code {e.returncode}: {error_output}")

def run_and_parse_json(command_list: List[str], timeout: Optional[int] = None) -> Dict:
    """Runs a command and safely parses its JSON output."""
    raw_output = run_command(command_list, timeout=timeout)
    if not raw_output:
        return {}
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        try:
            data = json.loads(raw_output)
            if data.get("bearer_error") or data.get("vnstat_error"):
                return data
        except json.JSONDecodeError:
            pass
        
        error_msg = f"Failed to parse JSON from command: {' '.join(command_list)}"
        log_message("ERROR", f"{error_msg}\nRaw Output: {raw_output}")
        raise Exception(f"{error_msg}. Check logs for details.")

# --- Port and Config Management ---
def get_or_create_proxy_config(interface_name: str, all_configs: Dict) -> Tuple[Dict, bool]:
    """
    Gets an existing proxy config or generates a new one with non-overlapping port ranges.
    This is the corrected logic.
    """
    if interface_name in all_configs and all(k in all_configs[interface_name] for k in ['httpPort', 'socksPort']):
        return all_configs[interface_name], False

    used_http_ports = {c.get('httpPort') for c in all_configs.values() if c.get('httpPort')}
    used_socks_ports = {c.get('socksPort') for c in all_configs.values() if c.get('socksPort')}
    
    # Find available HTTP port independently
    http_port = CONFIG['HTTP_PORT_RANGE_START']
    while http_port in used_http_ports:
        http_port += 1
        if http_port > CONFIG['HTTP_PORT_RANGE_END']:
            raise Exception("No available HTTP ports in the specified range.")

    # Find available SOCKS port independently
    socks_port = CONFIG['SOCKS_PORT_RANGE_START']
    while socks_port in used_socks_ports:
        socks_port += 1
        if socks_port > CONFIG['SOCKS_PORT_RANGE_END']:
            raise Exception("No available SOCKS ports in the specified range.")
    
    new_config = {
        "httpPort": http_port,
        "socksPort": socks_port, 
        "username": f"user_{secrets.token_hex(2)}",
        "password": secrets.token_hex(8),
        "customName": None
    }
    
    log_message("INFO", f"Generated new proxy config for {interface_name} on HTTP Port:{new_config['httpPort']} / SOCKS Port:{new_config['socksPort']}")
    return new_config, True

# --- 3Proxy Config File Generation ---
def generate_3proxy_config_content(config: Dict, egress_ip: str) -> Optional[str]:
    """Generates the content for a 3proxy configuration file based on the user's proven example."""
    if not egress_ip or not config.get('httpPort') or not config.get('socksPort'):
        return None

    username = config.get('username')
    password = config.get('password')
    http_port = config['httpPort']
    socks_port = config['socksPort']
    listening_ip = "0.0.0.0"

    lines = [
        "nscache 65536",
        "nserver 8.8.8.8",
        "nserver 8.8.4.4",
        "timeouts 1 5 30 60 180 1800 15 60",
        "daemon",
    ]

    is_authenticated = bool(username and password)

    if is_authenticated:
        lines.extend([
            f"users {username}:CL:{password}",
            "auth strong",
            f"allow {username}"
        ])
    else:
        lines.append("auth none")

    proxy_flags = "-n"
    if not is_authenticated:
        proxy_flags += " -a"

    socks_flags = ""
    if not is_authenticated:
        socks_flags += " -a"

    lines.extend([
        f"proxy {proxy_flags} -p{http_port} -i{listening_ip} -e{egress_ip}",
        f"socks {socks_flags} -p{socks_port} -i{listening_ip} -e{egress_ip}",
        "flush"
    ])
    
    return "\n".join(lines)


def write_3proxy_config_file(interface_name: str, egress_ip: str) -> Optional[str]:
    """Writes a 3proxy configuration file for a given modem interface."""
    try:
        all_configs = read_state_file(CONFIG['PROXY_CONFIGS_FILE'])
        interface_config = all_configs.get(interface_name)
        if not interface_config:
            raise Exception(f"No configuration found for {interface_name}")
        
        config_content = generate_3proxy_config_content(interface_config, egress_ip)
        if not config_content:
            log_message("WARN", f"Could not generate config for {interface_name} (missing IP?). Skipping write.")
            return None

        config_file_path = CONFIG['THREPROXY_CONFIG_DIR'] / f"{interface_name}.cfg"
        temp_file = config_file_path.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            f.write(config_content)
        temp_file.replace(config_file_path)

        log_message("DEBUG", f"Wrote 3proxy config for {interface_name}.")
        return str(config_file_path)
    except Exception as e:
        log_message("ERROR", f"Failed to write 3proxy config for {interface_name}: {e}")
        raise

# --- Core Logic Functions ---
def is_command_available(command):
    return shutil.which(command) is not None

def get_proxy_status(interface_name: str) -> str:
    """Checks if the 3proxy service for a specific interface is active."""
    # This command is expected to fail if the service is not active.
    # We suppress the exception and check the output.
    result = run_command(
        ['systemctl', 'is-active', '--quiet', f"3proxy@{interface_name}.service"], 
        check=False, 
        suppress_error=True
    )
    if result == 'active':
        return 'running'
    else:
        return 'stopped'


def get_public_ip(interface_name: str) -> Optional[str]:
    """Gets the public IP address for a specific network interface."""
    if not is_command_available("curl"): return None
    try:
        # Add a longer timeout for curl
        return run_command(['curl', '--interface', interface_name, '--connect-timeout', '10', 'https://api.ipify.org'], timeout=20)
    except Exception:
        return None

def get_primary_lan_ip() -> Optional[str]:
    """Finds the primary non-modem LAN IP address of the server."""
    try:
        interfaces = run_and_parse_json(['ip', '-j', 'addr'])
        modem_pattern = re.compile(r'^(enx|usb|wwan|ppp)')
        excluded_pattern = re.compile(r'^(lo|docker|veth|br-|cali|vxlan)')
        
        candidate_ips = []
        for iface in interfaces:
            ifname = iface.get('ifname', '')
            if iface.get('operstate') == 'UP' and not excluded_pattern.match(ifname) and not modem_pattern.match(ifname):
                for addr_info in iface.get('addr_info', []):
                    if addr_info.get('family') == 'inet':
                        candidate_ips.append(addr_info.get('local'))

        return candidate_ips[0] if candidate_ips else None
    except Exception as e:
        log_message("WARN", f"Could not determine primary LAN IP: {e}")
        return None

def get_all_modem_statuses() -> Dict:
    """The main function to aggregate all modem and proxy information."""
    try:
        interfaces = run_and_parse_json(['ip', '-j', 'addr'])
        modem_pattern = re.compile(r'^(enx|usb|wwan|ppp)')
        all_modems = {}
        server_lan_ip = get_primary_lan_ip()

        for iface in interfaces:
            ifname = iface.get('ifname', '')
            if modem_pattern.match(ifname):
                ip_address = next((addr.get('local') for addr in iface.get('addr_info', []) if addr.get('family') == 'inet'), None)
                status = 'connected' if iface.get('operstate') == 'UP' and ip_address else 'disconnected'
                all_modems[ifname] = {
                    "id": iface.get('address', ifname), "name": f"Modem ({ifname})", "interfaceName": ifname,
                    "status": status, "ipAddress": ip_address, "source": "ip_addr", "serverLanIp": server_lan_ip
                }
        
        if is_command_available("mmcli"):
            try:
                mm_list = run_and_parse_json(['mmcli', '-L', '-J'])
                for modem_path in mm_list.get('modem-list', []):
                    details = run_and_parse_json(['mmcli', '-m', modem_path, '-J'])
                    ifname = details.get('modem', {}).get('generic', {}).get('primary-port')
                    if ifname and ifname in all_modems:
                        all_modems[ifname]['id'] = details.get('modem', {}).get('generic', {}).get('device-identifier', ifname)
                        all_modems[ifname]['name'] = details.get('modem',{}).get('device-properties',{}).get('device.product', f"Modem ({ifname})")
                        all_modems[ifname]['source'] = "mmcli_enhanced"
            except Exception as e:
                log_message("WARN", f"Could not enhance with mmcli data: {e}")

        status_list = list(all_modems.values())
        proxy_configs = read_state_file(CONFIG['PROXY_CONFIGS_FILE'])
        configs_changed = False
        
        for modem in status_list:
            # We need to pass the full dict to modify it
            cfg, created = get_or_create_proxy_config(modem['interfaceName'], proxy_configs)
            if created:
                proxy_configs[modem['interfaceName']] = cfg
                configs_changed = True
            
            # Ensure the config on the modem object is the most up-to-date one
            modem['proxyConfig'] = proxy_configs.get(modem['interfaceName'])
            if modem['proxyConfig'] and modem['proxyConfig'].get('customName'):
                 modem['name'] = modem['proxyConfig']['customName']
            
            if modem['status'] == 'connected' and modem['ipAddress']:
                modem['publicIpAddress'] = get_public_ip(modem['interfaceName'])
                modem['proxyStatus'] = get_proxy_status(modem['interfaceName'])
                if modem['proxyStatus'] == 'stopped': # Only write if stopped to avoid race conditions
                    write_3proxy_config_file(modem['interfaceName'], modem['ipAddress'])
            else:
                modem['publicIpAddress'] = None
                modem['proxyStatus'] = 'stopped'
        
        if configs_changed:
            write_state_file(CONFIG['PROXY_CONFIGS_FILE'], proxy_configs)
        
        return {"success": True, "data": status_list}
    except Exception as e:
        log_message("ERROR", f"Critical error in get_all_modem_statuses: {e}")
        return {"success": False, "error": str(e)}

def proxy_action(action: str, interface_name: str) -> Dict:
    """Handles start, stop, and restart actions for a proxy service."""
    try:
        service_name = f"3proxy@{interface_name}.service"
        log_message("INFO", f"Attempting to {action} proxy for {interface_name}.")
        run_command(['systemctl', action, service_name])
        return {"success": True, "message": f"Proxy action '{action}' successful for {interface_name}."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def rotate_ip(interface_name: str) -> Dict:
    """Disconnects and reconnects a modem via mmcli to get a new IP address."""
    try:
        modem_path = _get_modem_path_for_interface(interface_name)

        modem_details = run_and_parse_json(['mmcli', '-m', modem_path, '-J'])
        bearer_path = modem_details.get('modem', {}).get('generic', {}).get('bearers', [None])[0]
        if not bearer_path:
            raise Exception("Modem has no active data bearer/connection to disconnect.")
        
        log_message("INFO", f"Rotating IP for {interface_name}: Disconnecting bearer {bearer_path}")
        run_command(['mmcli', '-b', bearer_path, '--disconnect'])
        time.sleep(5) 
        log_message("INFO", f"Rotating IP for {interface_name}: Reconnecting bearer {bearer_path}")
        run_command(['mmcli', '-b', bearer_path, '--connect'])
        
        time.sleep(10)
        
        all_statuses = get_all_modem_statuses()
        if not all_statuses.get('success'):
            raise Exception("Failed to get modem statuses after reconnection.")
        
        new_status = next((m for m in all_statuses['data'] if m['interfaceName'] == interface_name), None)
        if not new_status or not new_status.get('ipAddress'):
            raise Exception("Modem reconnected but failed to acquire a new IP address.")
            
        new_ip = new_status['ipAddress']
        log_message("INFO", f"IP rotation for {interface_name} successful. New IP: {new_ip}")
        # Automatically restart proxy to bind to the new IP if it was running
        if new_status.get('proxyStatus') == 'running':
            log_message("INFO", f"Proxy for {interface_name} was running, restarting it to apply new IP.")
            proxy_action('restart', interface_name)
        return {"success": True, "newIp": new_ip}
    except Exception as e:
        log_message("ERROR", f"Failed to rotate IP for {interface_name}: {e}")
        return {"success": False, "error": str(e)}

def get_all_configs() -> Dict:
    """Returns all stored proxy configurations."""
    return {"success": True, "data": read_state_file(CONFIG['PROXY_CONFIGS_FILE'])}

def update_proxy_config(interface_name: str, config_update: Dict) -> Dict:
    """Updates the configuration for a specific proxy and restarts it."""
    try:
        all_configs = read_state_file(CONFIG['PROXY_CONFIGS_FILE'])
        if interface_name not in all_configs:
            return {"success": False, "error": "Proxy config not found."}
        
        allowed_keys = ['username', 'password', 'customName']
        for key, value in config_update.items():
            if key in allowed_keys:
                all_configs[interface_name][key] = value

        write_state_file(CONFIG['PROXY_CONFIGS_FILE'], all_configs)
        
        # Check current status before restarting
        current_status = get_proxy_status(interface_name)
        if current_status == 'running':
            log_message("INFO", f"Restarting proxy for {interface_name} to apply config changes.")
            restart_result = proxy_action('restart', interface_name)
            if not restart_result['success']:
                raise Exception(f"Config updated, but failed to restart proxy: {restart_result.get('error')}")
            return {"success": True, "message": "Configuration updated and proxy restarted."}
        else:
            # If proxy is stopped, just update the config file
            all_statuses = get_all_modem_statuses()
            modem_info = next((m for m in all_statuses.get('data', []) if m['interfaceName'] == interface_name), None)
            if modem_info and modem_info.get('ipAddress'):
                 write_3proxy_config_file(interface_name, modem_info['ipAddress'])
            return {"success": True, "message": "Configuration updated. Start the proxy to apply changes."}

    except Exception as e:
        return {"success": False, "error": str(e)}

# --- Vnstat Functions ---
def get_vnstat_interfaces() -> Dict:
    """Gets the list of interfaces monitored by vnstat."""
    try:
        if not is_command_available("vnstat"):
            raise Exception("vnstat command is not installed.")
        
        vnstat_data = run_and_parse_json(['vnstat', '-J'])
        interfaces = [iface['name'] for iface in vnstat_data.get('interfaces', [])]
        return {"success": True, "data": interfaces}
    except Exception as e:
        log_message("WARN", f"Could not get vnstat interfaces: {e}. Is vnstat running and has data?")
        return {"success": True, "data": []} # Return empty list on failure, not an error

def get_vnstat_stats(interface_name: str) -> Dict:
    """Gets all traffic stats for a specific interface from vnstat."""
    try:
        vnstat_data = run_and_parse_json(['vnstat', '-i', interface_name, '--json', 'f'])
        if not vnstat_data:
            raise Exception("No data returned from vnstat for this interface.")
            
        interface_data = next((iface for iface in vnstat_data.get('interfaces', []) if iface.get('name') == interface_name), None)
        if not interface_data:
            raise Exception("Interface not found in vnstat output.")
            
        stats = {
            "name": interface_data.get('name'),
            "totalrx": interface_data.get('traffic', {}).get('total', {}).get('rx', 0),
            "totaltx": interface_data.get('traffic', {}).get('total', {}).get('tx', 0),
            "day": interface_data.get('traffic', {}).get('day', []),
            "month": interface_data.get('traffic', {}).get('month', []),
            "hour": interface_data.get('traffic', {}).get('hour', []),
        }
        return {"success": True, "data": stats}
    except Exception as e:
        return {"success": False, "error": str(e)}
        
# --- Modem Actions (SMS/USSD) ---
def send_sms(interface_name: str, args: Dict) -> Dict:
    """Sends an SMS message."""
    try:
        modem_path = _get_modem_path_for_interface(interface_name)
        recipient = args.get('recipient')
        message = args.get('message')
        if not recipient or not message:
            raise ValueError("Recipient and message are required.")
            
        sms_create_cmd = ['mmcli', '-m', modem_path, f'--messaging-create-sms=text="{message}",number="{recipient}"']
        sms_path_output = run_command(sms_create_cmd)
        
        sms_path_match = re.search(r'(/org/freedesktop/ModemManager1/SMS/\d+)', sms_path_output)
        if not sms_path_match:
            raise Exception(f"Could not parse SMS path from output: {sms_path_output}")
        sms_path = sms_path_match.group(1)
        
        run_command(['mmcli', '-s', sms_path, '--send'])
        log_message("INFO", f"SMS sent successfully via {interface_name} to {recipient}")
        return {"success": True, "message": f"SMS sent to {recipient}"}
    except Exception as e:
        log_message("ERROR", f"Failed to send SMS via {interface_name}: {e}")
        return {"success": False, "error": str(e)}

def read_sms(interface_name: str) -> Dict:
    """Reads SMS messages."""
    try:
        modem_path = _get_modem_path_for_interface(interface_name)
        sms_list = run_and_parse_json(['mmcli', '-m', modem_path, '--messaging-list-sms', '-J'])
        
        messages = []
        for sms_path in sms_list.get('modem', {}).get('messaging', {}).get('sms', []):
            sms_details = run_and_parse_json(['mmcli', '-s', sms_path, '-J'])
            content = sms_details.get('sms', {}).get('content', {})
            messages.append({
                "id": sms_path,
                "from": content.get('number'),
                "timestamp": content.get('timestamp'),
                "content": content.get('text'),
            })
        return {"success": True, "data": messages}
    except Exception as e:
        log_message("ERROR", f"Failed to read SMS from {interface_name}: {e}")
        return {"success": False, "error": str(e)}

def send_ussd(interface_name: str, args: Dict) -> Dict:
    """Sends a USSD command."""
    try:
        modem_path = _get_modem_path_for_interface(interface_name)
        ussd_code = args.get('ussdCode')
        if not ussd_code:
            raise ValueError("USSD code is required.")

        initiate_cmd = ['mmcli', '-m', modem_path, f'--3gpp-ussd-initiate={ussd_code}']
        response = run_command(initiate_cmd)
        return {"success": True, "response": response}
    except Exception as e:
        log_message("ERROR", f"Failed to send USSD via {interface_name}: {e}")
        return {"success": False, "error": str(e)}

def _get_modem_path_for_interface(interface_name: str) -> str:
    """Helper to find a modem's D-Bus path from its network interface name."""
    mm_list = run_and_parse_json(['mmcli', '-L', '-J'])
    for modem_path in mm_list.get('modem-list', []):
        details = run_and_parse_json(['mmcli', '-m', modem_path, '-J'])
        if details.get('modem', {}).get('generic', {}).get('primary-port') == interface_name:
            return modem_path
    raise Exception(f"No ModemManager modem found for interface {interface_name}")

# --- Tunnel Management ---
def get_available_cloudflare_tunnels():
    """Gets list of available (configured) Cloudflare tunnels."""
    try:
        if not is_command_available('cloudflared'):
            return {"success": True, "data": []}
        tunnels_raw = run_command(['cloudflared', 'tunnel', 'list', '--output', 'json'], check=True)
        tunnels_list = json.loads(tunnels_raw)
        
        active_tunnels = [
            {"id": t['id'], "name": t['name']} 
            for t in tunnels_list 
            if t.get('status') == 'healthy'
        ]
        return {"success": True, "data": active_tunnels}
    except Exception as e:
        log_message("WARN", f"Could not get Cloudflare tunnels: {e}")
        return {"success": True, "data": []}

def get_all_tunnel_statuses():
    """Reads the tunnel PID file and checks which tunnels are active."""
    pids = read_state_file(CONFIG['TUNNEL_PIDS_FILE'], {})
    statuses = []
    
    for tunnel_id, info in pids.items():
        status = 'inactive'
        try:
            os.kill(info['pid'], 0)
            status = 'active'
        except OSError:
            pass
            
        statuses.append({
            "id": tunnel_id,
            "type": info.get('type', 'Ngrok'),
            "status": status,
            "url": info.get('url'),
            "localPort": info['localPort'],
            "linkedTo": info.get('linkedTo')
        })
    return {"success": True, "data": statuses}

def start_tunnel(tunnel_id, local_port, linked_to, tunnel_type, cloudflare_id=None):
    """Starts a tunnel process (Ngrok or Cloudflare)."""
    pids = read_state_file(CONFIG['TUNNEL_PIDS_FILE'], {})
    if tunnel_id in pids:
        try:
            os.kill(pids[tunnel_id]['pid'], 0)
            log_message("INFO", f"Tunnel {tunnel_id} is already running.")
            return {"success": True, "message": "Tunnel already running."}
        except OSError:
            pass

    log_message("INFO", f"Starting {tunnel_type} tunnel '{tunnel_id}' for port {local_port}.")
    
    if tunnel_type == 'Cloudflare':
        if not cloudflare_id:
            raise ValueError("Cloudflare tunnel ID is required.")
        cmd = f"nohup pkexec cloudflared tunnel run --url http://localhost:{local_port} {cloudflare_id} > /dev/null 2>&1 & echo $!"
    else: # Default to Ngrok
        cmd = f"nohup ngrok http {local_port} --log=stdout > /tmp/ngrok_{tunnel_id}.log 2>&1 & echo $!"

    try:
        pid = int(subprocess.check_output(cmd, shell=True, text=True).strip())
        
        pids[tunnel_id] = {
            "pid": pid,
            "localPort": local_port,
            "linkedTo": linked_to,
            "type": tunnel_type,
            "url": None
        }

        if tunnel_type == 'Ngrok':
            time.sleep(3) 
            try:
                with open(f'/tmp/ngrok_{tunnel_id}.log', 'r') as log_file:
                    for line in log_file:
                        if "url=" in line:
                            match = re.search(r'url=(https?://[^\s]+)', line)
                            if match:
                                pids[tunnel_id]['url'] = match.group(1)
                                break
            except FileNotFoundError:
                log_message("WARN", f"Ngrok log file for {tunnel_id} not found.")

        write_state_file(CONFIG['TUNNEL_PIDS_FILE'], pids)
        return {"success": True, "message": "Tunnel started."}
    except Exception as e:
        log_message("ERROR", f"Failed to start tunnel {tunnel_id}: {e}")
        return {"success": False, "error": str(e)}

def stop_tunnel(tunnel_id):
    """Stops a running tunnel process."""
    pids = read_state_file(CONFIG['TUNNEL_PIDS_FILE'], {})
    if tunnel_id in pids:
        pid = pids[tunnel_id]['pid']
        try:
            run_command(['kill', '-9', str(pid)])
            log_message("INFO", f"Stopped tunnel {tunnel_id} (PID: {pid}).")
        except Exception as e:
            log_message("WARN", f"Could not kill tunnel {tunnel_id} (PID: {pid}), it might already be stopped. Error: {e}")
        
        del pids[tunnel_id]
        write_state_file(CONFIG['TUNNEL_PIDS_FILE'], pids)
        return {"success": True, "message": "Tunnel stopped."}
    return {"success": False, "error": "Tunnel not found."}


# --- System Logs ---
def get_logs() -> Dict:
    """Reads and returns the content of the log file."""
    try:
        log_file_path = CONFIG.get('LOG_FILE')
        if not log_file_path or not log_file_path.exists():
            return {"success": True, "data": []}
        
        with open(log_file_path, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                logs = [json.loads(line) for line in f if line.strip()]
                return {"success": True, "data": logs}
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- Main Dispatcher ---
def main():
    """Main entry point that dispatches actions."""
    initialize_environment()
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "No action specified"}))
        sys.exit(1)

    action = sys.argv[1]
    args = sys.argv[2:]
    result = {}
    
    try:
        log_message("DEBUG", f"Backend action '{action}' called.")
        
        action_map = {
            'get_all_modem_statuses': lambda: get_all_modem_statuses(),
            'start_proxy': lambda: proxy_action('start', args[0]),
            'stop_proxy': lambda: proxy_action('stop', args[0]),
            'restart_proxy': lambda: proxy_action('restart', args[0]),
            'rotate_ip': lambda: rotate_ip(args[0]),
            'get_all_configs': lambda: get_all_configs(),
            'update_proxy_config': lambda: update_proxy_config(args[0], json.loads(args[1])),
            'get_vnstat_interfaces': lambda: get_vnstat_interfaces(),
            'get_vnstat_stats': lambda: get_vnstat_stats(args[0]),
            'send_sms': lambda: send_sms(args[0], json.loads(args[1])),
            'read_sms': lambda: read_sms(args[0]),
            'send_ussd': lambda: send_ussd(args[0], json.loads(args[1])),
            'get_logs': lambda: get_logs(),
            'get_available_cloudflare_tunnels': lambda: get_available_cloudflare_tunnels(),
            'get_all_tunnel_statuses': lambda: get_all_tunnel_statuses(),
            'start_tunnel': lambda: start_tunnel(args[0], int(args[1]), args[2], args[3], args[4] if len(args) > 4 else None),
            'stop_tunnel': lambda: stop_tunnel(args[0]),
        }

        # Simplified action names from frontend
        if action == "start": action = "start_proxy"
        if action == "stop": action = "stop_proxy"
        if action == "restart": action = "restart_proxy"

        if action in action_map:
            result = action_map[action]()
        else:
            result = {"success": False, "error": f"Unknown action: {action}"}
            
    except Exception as e:
        log_message("ERROR", f"Unhandled error executing action '{action}': {e}")
        result = {"success": False, "error": str(e), "type": type(e).__name__}
    
    print(json.dumps(result, indent=None))

if __name__ == "__main__":
    main()
