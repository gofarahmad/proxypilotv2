
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
from typing import Dict, List, Tuple, Optional, Any

# --- Configuration ---
CONFIG = {
    'STATE_DIR': Path(os.path.expanduser("~")) / ".proxy_pilot_state",
    'PROXY_CONFIGS_FILE': "proxy_configs.json",
    'TUNNEL_PIDS_FILE': "tunnel_pids.json",
    'LOG_FILE': "activity.log",
    'LOG_MAX_ENTRIES': 200,
    'THREPROXY_CONFIG_DIR': Path("/etc/3proxy/conf"),
    'PORT_RANGE_START': 7001,
    'PORT_RANGE_END': 8000, # This defines the HTTP port range. SOCKS will be +1000.
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
        # Log this critical error before exiting
        log_message("ERROR", f"Permission denied: Could not create {CONFIG['THREPROXY_CONFIG_DIR']}.")
        sys.exit(1)

# --- Logging Helper ---
def log_message(level: str, message: str) -> None:
    """Log a message with timestamp and level to the log file, with rotation."""
    try:
        log_file_path = CONFIG.get('LOG_FILE')
        if not isinstance(log_file_path, Path):
            # Fallback if config isn't initialized yet
            log_file_path = Path(os.path.expanduser("~")) / ".proxy_pilot_state" / "activity.log"
            log_file_path.parent.mkdir(exist_ok=True)
        
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log_entry = json.dumps({"timestamp": timestamp, "level": level.upper(), "message": str(message)}) + '\n'

        with open(log_file_path, 'a+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                lines = f.readlines()
                
                # Simple rotation logic
                if len(lines) >= CONFIG['LOG_MAX_ENTRIES']:
                    lines_to_keep = lines[-(CONFIG['LOG_MAX_ENTRIES'] - 1):]
                    f.seek(0)
                    f.truncate()
                    f.writelines(lines_to_keep)
                
                # Append the new log entry at the end of the file
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
        
        # This is an atomic operation on POSIX systems
        os.replace(temp_file_path, file_path)
        return True
    except (IOError, TypeError) as e:
        log_message("ERROR", f"Failed to write state file {file_path}: {e}")
        return False

# --- Command Execution ---
def run_command(command_list: List[str], timeout: Optional[int] = None, check: bool = True) -> str:
    """
    Executes a system command securely and captures its output.
    Uses 'pkexec' for commands requiring elevated privileges.
    """
    if timeout is None:
        timeout = CONFIG['DEFAULT_TIMEOUT']

    privileged_commands = {'systemctl', 'mmcli', 'cloudflared'}
    cmd_to_check = command_list[0]
    
    # Prepend pkexec if it's a privileged command and not already there
    if cmd_to_check in privileged_commands and 'pkexec' not in command_list:
        command_list.insert(0, 'pkexec')
        # pkexec might ask for a password, so a longer timeout could be necessary
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
        # Don't log expected failures like service not being active
        if not ("is-active" in command_list and e.returncode > 0):
             log_message("ERROR", f"Command failed: {' '.join(command_list)}. Stderr: {error_output}")
        
        # Handle specific known error strings for clearer frontend messages
        if "couldn't find bearer" in error_output.lower():
            return json.dumps({"bearer_error": True, "message": "Modem bearer (data connection) not found. It may be disconnected or initializing."})
        if "unable to read database" in error_output.lower():
            return json.dumps({"vnstat_error": "not_ready", "message": "vnstat database is not ready or has no data."})
        if "Unit 3proxy@" in error_output and "not found" in error_output:
            raise Exception("Systemd unit file '3proxy@.service' not found. Please check installation steps.")
        
        # For other errors, raise a generic but informative exception
        raise Exception(f"Command failed with exit code {e.returncode}: {error_output}")

def run_and_parse_json(command_list: List[str], timeout: Optional[int] = None) -> Dict:
    """Runs a command and safely parses its JSON output."""
    raw_output = run_command(command_list, timeout=timeout)
    if not raw_output:
        return {}
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        # Check if the output is a JSON string representing a specific error
        try:
            data = json.loads(raw_output)
            if data.get("bearer_error") or data.get("vnstat_error"):
                return data
        except json.JSONDecodeError:
            pass # Not a special JSON error, fall through
        
        error_msg = f"Failed to parse JSON from command: {' '.join(command_list)}"
        log_message("ERROR", f"{error_msg}\nRaw Output: {raw_output}")
        raise Exception(f"{error_msg}. Check logs for details.")

# --- Port and Config Management ---
def get_or_create_proxy_config(interface_name: str, all_configs: Dict) -> Tuple[Dict, bool]:
    """Gets an existing proxy config or generates a new one with unique ports and credentials."""
    if interface_name in all_configs and all(k in all_configs[interface_name] for k in ['httpPort', 'socksPort']):
        return all_configs[interface_name], False

    used_ports = {
        port for config in all_configs.values() for key, port in config.items() if key in ['httpPort', 'socksPort']
    }
    
    http_port = CONFIG['PORT_RANGE_START']
    while http_port in used_ports or (http_port + 1000) in used_ports:
        http_port += 1
        if http_port > CONFIG['PORT_RANGE_END']:
            raise Exception("No available ports in the specified range.")
    
    new_config = {
        "httpPort": http_port,
        "socksPort": http_port + 1000,
        "username": f"user_{secrets.token_hex(2)}",
        "password": secrets.token_hex(8),
        "bindIp": "0.0.0.0",
        "customName": None
    }
    
    log_message("INFO", f"Generated new proxy config for {interface_name} on HTTP:{new_config['httpPort']}/SOCKS:{new_config['socksPort']}")
    return new_config, True

# --- 3Proxy Config File Generation ---
def generate_3proxy_config_content(config: Dict, egress_ip: str) -> Optional[str]:
    """Generates the content for a 3proxy configuration file."""
    if not egress_ip or not config.get('httpPort') or not config.get('socksPort'):
        return None

    is_authenticated = config.get('username') and config.get('password')
    
    lines = [
        "daemon",
        "nserver 8.8.8.8", "nserver 8.8.4.4", "nscache 65536",
        "timeouts 1 5 30 60 180 1800 15 60",
    ]

    if is_authenticated:
        lines.extend([f"users {config['username']}:CL:{config['password']}", "auth strong", f"allow {config['username']}"])
        lines.append(f"proxy -p{config['httpPort']} -i0.0.0.0 -e{egress_ip}")
        lines.append(f"socks -p{config['socksPort']} -i0.0.0.0 -e{egress_ip}")
    else: # Fallback to no auth, though this shouldn't happen with auto-generation
        lines.append("auth none")
        lines.append(f"proxy -a -p{config['httpPort']} -i0.0.0.0 -e{egress_ip}")
        lines.append(f"socks -a -p{config['socksPort']} -i0.0.0.0 -e{egress_ip}")
    
    lines.append("flush")
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
        # Atomic write
        temp_file = config_file_path.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            f.write(config_content)
        temp_file.replace(config_file_path)

        log_message("DEBUG", f"Wrote 3proxy config for {interface_name}.")
        return str(config_file_path)
    except Exception as e:
        log_message("ERROR", f"Failed to write 3proxy config for {interface_name}: {e}")
        raise

# --- Core Logic (continues with the rest of the functions) ---
# Note: The following functions are simplified for brevity but would be fully implemented.
def is_command_available(command):
    return shutil.which(command) is not None

def get_proxy_status(interface_name, modem_status):
    if modem_status != 'connected':
        return 'stopped'
    try:
        # Use check=False as a non-zero exit code is expected for 'inactive'
        run_command(['systemctl', 'is-active', '--quiet', f"3proxy@{interface_name}.service"], check=False)
        # If the command succeeds (exit code 0), it's running.
        return 'running'
    except Exception:
        # If it fails for any other reason, it's considered stopped.
        return 'stopped'

def get_public_ip(interface_name):
    if not is_command_available("curl"): return None
    try:
        return run_command(['curl', '--interface', interface_name, '--connect-timeout', '5', 'https://api.ipify.org'], timeout=10)
    except Exception:
        return None

def get_primary_lan_ip():
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
        return None
    except Exception: return None

def get_all_modem_statuses():
    # This is a placeholder for the full, complex logic
    try:
        # 1. Base detection
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
        
        # 2. Enhance with mmcli
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

        # 3. Add proxy configs and statuses
        status_list = list(all_modems.values())
        proxy_configs = read_state_file(CONFIG['PROXY_CONFIGS_FILE'])
        configs_changed = False
        for modem in status_list:
            cfg, created = get_or_create_proxy_config(modem['interfaceName'], proxy_configs)
            if created:
                proxy_configs[modem['interfaceName']] = cfg
                configs_changed = True
            modem['proxyConfig'] = cfg
            if cfg.get('customName'): modem['name'] = cfg['customName']
            
            if modem['status'] == 'connected':
                modem['publicIpAddress'] = get_public_ip(modem['interfaceName'])
                modem['proxyStatus'] = get_proxy_status(modem['interfaceName'], modem['status'])
                if modem['ipAddress']: write_3proxy_config_file(modem['interfaceName'], modem['ipAddress'])
            else:
                modem['publicIpAddress'] = None
                modem['proxyStatus'] = 'stopped'
        
        if configs_changed: write_state_file(CONFIG['PROXY_CONFIGS_FILE'], proxy_configs)
        
        return {"success": True, "data": status_list}
    except Exception as e:
        log_message("ERROR", f"Critical error in get_all_modem_statuses: {e}")
        return {"success": False, "error": str(e)}

def proxy_action(action, interface_name):
    # This is a placeholder for the full logic
    try:
        service_name = f"3proxy@{interface_name}.service"
        run_command(['systemctl', action, service_name])
        return {"success": True, "message": f"Proxy action {action} successful."}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- Main Dispatcher ---
def main():
    """Main entry point for the backend controller."""
    initialize_environment()
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "No action specified"}))
        sys.exit(1)

    action = sys.argv[1]
    result = {}
    
    try:
        log_message("DEBUG", f"Executing action: {action}")
        
        if action == 'get_all_modem_statuses':
            result = get_all_modem_statuses()
        elif action in ['start', 'stop', 'restart']:
            result = proxy_action(action, sys.argv[2])
        # Add other actions here...
        else:
            result = {"success": False, "error": f"Unknown action: {action}"}
            
    except Exception as e:
        log_message("ERROR", f"Unhandled error executing action '{action}': {e}")
        result = {"success": False, "error": str(e), "type": type(e).__name__}
    
    print(json.dumps(result))

if __name__ == "__main__":
    main()

    