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
import fcntl
import time
from typing import Dict, List, Optional, Any
import requests
from lxml import html

# --- Configuration ---
CONFIG = {
    'STATE_DIR': Path(os.path.expanduser("~")) / ".proxy_pilot_state",
    'PROXY_CONFIGS_FILE': "proxy_configs.json",
    'LOG_FILE': "activity.log",
    'LOG_MAX_ENTRIES': 200,
    'THREPROXY_CONFIG_DIR': Path("/etc/3proxy/conf"),
    'HTTP_PORT_RANGE_START': 7001,
    'HTTP_PORT_RANGE_END': 8000,
    'SOCKS_PORT_RANGE_START': 8001,
    'SOCKS_PORT_RANGE_END': 9000,
    'DEFAULT_TIMEOUT': 15,
    'HILINK_GATEWAY': "192.168.8.1"
}

# --- Initialization ---
def initialize_environment():
    CONFIG['STATE_DIR'].mkdir(exist_ok=True)
    CONFIG['PROXY_CONFIGS_FILE'] = CONFIG['STATE_DIR'] / CONFIG['PROXY_CONFIGS_FILE']
    CONFIG['LOG_FILE'] = CONFIG['STATE_DIR'] / CONFIG['LOG_FILE']
    try:
        CONFIG['THREPROXY_CONFIG_DIR'].mkdir(parents=True, exist_ok=True)
    except PermissionError:
        log_message("ERROR", f"Permission denied: Could not create {CONFIG['THREPROXY_CONFIG_DIR']}.")
        sys.exit(1)

# --- Logging & State Management (unchanged) ---
def log_message(level: str, message: str) -> None:
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

def read_state_file(file_path: Path, default_value: Any = None) -> Any:
    default_value = default_value if default_value is not None else {}
    if not file_path.exists(): return default_value
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try: return json.load(f)
            finally: fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, IOError): return default_value

def write_state_file(file_path: Path, data: Any) -> bool:
    try:
        temp_file_path = file_path.with_suffix(f'.tmp{os.getpid()}')
        with open(temp_file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        os.replace(temp_file_path, file_path)
        return True
    except (IOError, TypeError): return False

# --- HiLink Web UI Client ---
class HiLinkClient:
    def __init__(self, gateway=CONFIG['HILINK_GATEWAY']):
        self.base_url = f"http://{gateway}"
        self.session = requests.Session()

    def get_page(self, path):
        try:
            response = self.session.get(f"{self.base_url}/{path}", timeout=5)
            response.raise_for_status()
            return html.fromstring(response.content)
        except requests.RequestException as e:
            log_message("ERROR", f"Failed to get HiLink page {path}: {e}")
            raise Exception(f"Could not connect to modem at {self.base_url}. Is it connected and on the correct IP?")

    def get_info(self):
        device_info_tree = self.get_page("html/deviceinformation.html")
        antennapointing_tree = self.get_page("html/antennapointing.html")
        
        def get_text(tree, xpath, index=0):
            elements = tree.xpath(xpath)
            return elements[index].text_content().strip() if elements else "N/A"

        info = {
            "name": get_text(device_info_tree, '//tbody/tr[1]/td[2]'),
            "imei": get_text(device_info_tree, '//tbody/tr[3]/td[2]'),
            "network_mode": get_text(antennapointing_tree, '//*[@id="network_mode"]'),
            "operator": get_text(antennapointing_tree, '//*[@id="operator"]'),
            "connection_status": get_text(antennapointing_tree, '//*[@id="index_connection_status"]'),
            "rssi": get_text(antennapointing_tree, '//*[@id="rssi"]'),
            "rsrp": get_text(antennapointing_tree, '//*[@id="signal_table_value_1"]'),
            "sinr": get_text(antennapointing_tree, '//*[@id="signal_table_value_2"]'),
            "rsrq": get_text(antennapointing_tree, '//*[@id="signal_table_value_3"]'),
        }
        return info
        
# --- Command Execution & Port Management (for 3proxy) ---
def run_command(command_list: List[str], timeout: Optional[int] = None, check: bool = True, suppress_error: bool = False) -> str:
    if timeout is None: timeout = CONFIG['DEFAULT_TIMEOUT']
    try:
        result = subprocess.run(command_list, check=check, capture_output=True, text=True, timeout=timeout, encoding='utf-8', errors='replace')
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        error_output = e.stderr.strip() if hasattr(e, 'stderr') and e.stderr else "No error output."
        if suppress_error: return error_output
        raise Exception(f"Command failed: {command_list[0]}. Error: {error_output}")

def get_proxy_status(interface_name: str) -> str:
    try:
        result = run_command(['pkexec', 'systemctl', 'is-active', '--quiet', f"3proxy@{interface_name}.service"], check=False, suppress_error=True)
        return 'running' if result == 'active' else 'stopped'
    except Exception: return 'stopped'

def get_or_create_proxy_config(interface_name: str, all_configs: Dict) -> Tuple[Dict, bool]:
    if interface_name in all_configs: return all_configs[interface_name], False
    
    used_http_ports = {c.get('httpPort') for c in all_configs.values()}
    used_socks_ports = {c.get('socksPort') for c in all_configs.values()}

    http_port = next((p for p in range(CONFIG['HTTP_PORT_RANGE_START'], CONFIG['HTTP_PORT_RANGE_END']) if p not in used_http_ports), None)
    socks_port = next((p for p in range(CONFIG['SOCKS_PORT_RANGE_START'], CONFIG['SOCKS_PORT_RANGE_END']) if p not in used_socks_ports), None)

    if http_port is None or socks_port is None: raise Exception("No available ports in range.")
    
    new_config = {"httpPort": http_port, "socksPort": socks_port, "username": f"user_{secrets.token_hex(2)}", "password": secrets.token_hex(8), "customName": None}
    log_message("INFO", f"Generated new proxy config for {interface_name} on HTTP:{http_port}/SOCKS:{socks_port}")
    return new_config, True

def generate_3proxy_config_content(config: Dict, egress_ip: str) -> Optional[str]:
    # This function remains largely the same, as it's about 3proxy's format
    if not egress_ip or not config.get('httpPort') or not config.get('socksPort'): return None
    
    username, password = config.get('username'), config.get('password')
    lines = ["nscache 65536", "nserver 8.8.8.8", "nserver 8.8.4.4", "timeouts 1 5 30 60 180 1800 15 60", "daemon"]
    
    if username and password:
        lines.extend([f"users {username}:CL:{password}", "auth strong", f"allow {username}"])
    else:
        lines.append("auth none")
        
    proxy_flags = "-n" if username and password else "-n -a"
    lines.append(f"proxy {proxy_flags} -p{config['httpPort']} -i0.0.0.0 -e{egress_ip}")
    lines.append(f"socks -p{config['socksPort']} -i0.0.0.0 -e{egress_ip}")
    lines.append("flush")
    return "\n".join(lines)

def write_3proxy_config_file(interface_name: str, egress_ip: str) -> Optional[str]:
    try:
        all_configs = read_state_file(CONFIG['PROXY_CONFIGS_FILE'])
        config = all_configs.get(interface_name)
        if not config: raise Exception(f"No configuration found for {interface_name}")
        
        config_content = generate_3proxy_config_content(config, egress_ip)
        if not config_content: return None

        config_file_path = CONFIG['THREPROXY_CONFIG_DIR'] / f"{interface_name}.cfg"
        config_file_path.write_text(config_content)
        log_message("DEBUG", f"Wrote 3proxy config for {interface_name}.")
        return str(config_file_path)
    except Exception as e:
        log_message("ERROR", f"Failed to write 3proxy config for {interface_name}: {e}")
        raise

def get_primary_lan_ip() -> Optional[str]:
    try:
        interfaces = run_command(['ip', '-j', 'addr'])
        interfaces = json.loads(interfaces)
        modem_pattern = re.compile(r'^(enx|usb|wwan|ppp)')
        excluded_pattern = re.compile(r'^(lo|docker|veth|br-|cali|vxlan)')
        
        for iface in interfaces:
            ifname = iface.get('ifname', '')
            if iface.get('operstate') == 'UP' and not excluded_pattern.match(ifname) and not modem_pattern.match(ifname):
                for addr_info in iface.get('addr_info', []):
                    if addr_info.get('family') == 'inet':
                        return addr_info.get('local')
        return None
    except Exception: return None

# --- Core Logic ---
def get_all_modem_statuses() -> Dict:
    try:
        hilink_client = HiLinkClient()
        hilink_info = hilink_client.get_info()
        
        # We need a stable interface name. For HiLink, the gateway IP is the key.
        interface_name = f"hilink_{CONFIG['HILINK_GATEWAY'].replace('.', '_')}"
        
        # We still need the IP address from the server's perspective
        ip_info = json.loads(run_command(['ip', '-j', 'addr']))
        modem_ip = None
        for iface in ip_info:
            if iface.get('operstate') == 'UP' and any(addr.get('address', '').startswith('192.168.8.') for addr in iface.get('addr_info', [])):
                 modem_ip = next((addr.get('local') for addr in iface.get('addr_info', []) if addr.get('family') == 'inet'), None)
                 break
        
        modem_status = 'connected' if hilink_info['connection_status'].lower() == 'connected' else 'disconnected'
        
        proxy_configs = read_state_file(CONFIG['PROXY_CONFIGS_FILE'])
        cfg, created = get_or_create_proxy_config(interface_name, proxy_configs)
        if created:
            proxy_configs[interface_name] = cfg
            write_state_file(CONFIG['PROXY_CONFIGS_FILE'], proxy_configs)
        
        proxy_status = get_proxy_status(interface_name)
        if modem_status == 'connected' and modem_ip and proxy_status == 'stopped':
             write_3proxy_config_file(interface_name, modem_ip)

        # Structure the data similarly to the old format for frontend compatibility
        modem_data = {
            "id": hilink_info.get("imei", interface_name),
            "name": hilink_info.get("name", "HiLink Modem"),
            "interfaceName": interface_name,
            "status": modem_status,
            "ipAddress": modem_ip,
            "publicIpAddress": "N/A", # HiLink doesn't easily expose this to the OS
            "proxyStatus": proxy_status,
            "source": "hilink_webui",
            "proxyConfig": cfg,
            "serverLanIp": get_primary_lan_ip(),
            "details": { # Add all the rich details here
                "operator": hilink_info.get("operator"),
                "network_mode": hilink_info.get("network_mode"),
                "rssi": hilink_info.get("rssi"),
                "rsrp": hilink_info.get("rsrp"),
                "sinr": hilink_info.get("sinr"),
                "rsrq": hilink_info.get("rsrq"),
                "imei": hilink_info.get("imei"),
            }
        }
        
        return {"success": True, "data": [modem_data]}
    except Exception as e:
        log_message("ERROR", f"Critical error in get_all_modem_statuses: {e}")
        return {"success": False, "error": str(e)}

# --- Action Dispatcher ---
def main():
    initialize_environment()
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "No action specified"}))
        sys.exit(1)

    action = sys.argv[1]
    # args = sys.argv[2:]
    result = {}
    
    try:
        log_message("DEBUG", f"Backend action '{action}' called.")
        
        if action == 'get_all_modem_statuses':
            result = get_all_modem_statuses()
        else:
             result = {"success": False, "error": f"Action '{action}' is not yet implemented for HiLink modems."}
            
    except Exception as e:
        log_message("ERROR", f"Unhandled error executing action '{action}': {e}")
        result = {"success": False, "error": str(e), "type": type(e).__name__}
    
    print(json.dumps(result, indent=None))

if __name__ == "__main__":
    main()

    