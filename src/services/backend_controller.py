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
from typing import Dict, List, Optional, Any, Tuple
import requests
from lxml import html
import ipaddress

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

# --- Logging & State Management ---
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
    def __init__(self, gateway: str):
        self.base_url = f"http://{gateway}"
        self.session = requests.Session()

    def get_page(self, path):
        try:
            response = self.session.get(f"{self.base_url}/{path}", timeout=5)
            response.raise_for_status()
            return html.fromstring(response.content)
        except requests.RequestException as e:
            log_message("ERROR", f"Failed to get HiLink page {path} from {self.base_url}: {e}")
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
        if not suppress_error:
            raise Exception(f"Command failed: {command_list[0]}. Error: {error_output}")
        return error_output
    except Exception as e:
        if not suppress_error:
            raise Exception(f"An unexpected error occurred running command: {command_list[0]}. Error: {e}")
        return str(e)

def get_proxy_status(interface_name: str) -> str:
    try:
        # We need pkexec to run systemctl as root.
        result = run_command(['pkexec', 'systemctl', 'is-active', '--quiet', f"3proxy@{interface_name}.service"], suppress_error=True)
        return 'running' if 'active' in result else 'stopped'
    except Exception as e:
        log_message("ERROR", f"Failed to get proxy status for {interface_name}: {e}")
        return 'error'

def get_or_create_proxy_config(interface_name: str, all_configs: Dict) -> Tuple[Dict, bool]:
    if interface_name in all_configs: return all_configs[interface_name], False
    
    used_http_ports = {c.get('httpPort') for c in all_configs.values() if c.get('httpPort')}
    used_socks_ports = {c.get('socksPort') for c in all_configs.values() if c.get('socksPort')}

    http_port = next((p for p in range(CONFIG['HTTP_PORT_RANGE_START'], CONFIG['HTTP_PORT_RANGE_END']) if p not in used_http_ports), None)
    socks_port = next((p for p in range(CONFIG['SOCKS_PORT_RANGE_START'], CONFIG['SOCKS_PORT_RANGE_END']) if p not in used_socks_ports), None)

    if http_port is None or socks_port is None: raise Exception("No available ports in range.")
    
    new_config = {"httpPort": http_port, "socksPort": socks_port, "username": f"user_{secrets.token_hex(2)}", "password": secrets.token_hex(8), "customName": None}
    log_message("INFO", f"Generated new proxy config for {interface_name} on HTTP:{http_port}/SOCKS:{socks_port}")
    return new_config, True

def generate_3proxy_config_content(config: Dict, egress_ip: str) -> Optional[str]:
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
    
def discover_hilink_gateways() -> List[Tuple[str, str]]:
    """
    Discovers HiLink modem gateways by inspecting network interfaces.
    Returns a list of tuples, where each tuple is (interface_name, gateway_ip).
    """
    gateways = []
    try:
        ip_info = json.loads(run_command(['ip', '-j', 'addr']))
        for iface in ip_info:
            ifname = iface.get('ifname', '')
            # HiLink modems usually appear as 'enx...' or 'usb...'
            if iface.get('operstate') == 'UP' and (ifname.startswith('enx') or ifname.startswith('usb')):
                for addr_info in iface.get('addr_info', []):
                    if addr_info.get('family') == 'inet':
                        # Example: Server IP is 192.168.8.100, prefix is 24
                        # We derive the gateway is 192.168.8.1
                        server_ip = addr_info.get('local')
                        prefixlen = addr_info.get('prefixlen')
                        if server_ip and prefixlen:
                            try:
                                network = ipaddress.IPv4Interface(f"{server_ip}/{prefixlen}").network
                                # The gateway is typically the first usable IP in the subnet
                                gateway_ip = str(network[1])
                                gateways.append((ifname, gateway_ip))
                                log_message("DEBUG", f"Discovered potential HiLink gateway {gateway_ip} on interface {ifname}")
                            except ValueError as e:
                                log_message("WARN", f"Could not determine network for {server_ip}/{prefixlen}: {e}")
    except Exception as e:
        log_message("ERROR", f"Failed to discover HiLink gateways: {e}")
    return gateways

# --- Core Logic ---
def get_all_modem_statuses() -> Dict:
    all_modems_data = []
    proxy_configs = read_state_file(CONFIG['PROXY_CONFIGS_FILE'])
    
    discovered_gateways = discover_hilink_gateways()

    if not discovered_gateways:
        log_message("INFO", "No HiLink gateways discovered. If you have a modem connected, check its network interface state.")
        return {"success": True, "data": []}

    for ifname, gateway_ip in discovered_gateways:
        try:
            hilink_client = HiLinkClient(gateway=gateway_ip)
            hilink_info = hilink_client.get_info()
            
            # The interface name for HiLink is based on the gateway to ensure stability
            interface_name = f"hilink_{gateway_ip.replace('.', '_')}"
            
            modem_ip = next((addr['local'] for iface in json.loads(run_command(['ip', '-j', 'addr'])) if iface['ifname'] == ifname for addr in iface['addr_info'] if addr['family'] == 'inet'), None)
            
            modem_status = 'connected' if hilink_info.get('connection_status', '').lower() == 'connected' else 'disconnected'
            
            cfg, created = get_or_create_proxy_config(interface_name, proxy_configs)
            if created:
                proxy_configs[interface_name] = cfg
                write_state_file(CONFIG['PROXY_CONFIGS_FILE'], proxy_configs)
            
            proxy_status = get_proxy_status(interface_name)
            if modem_status == 'connected' and modem_ip and proxy_status == 'stopped':
                 write_3proxy_config_file(interface_name, modem_ip)

            modem_data = {
                "id": hilink_info.get("imei", interface_name),
                "name": cfg.get('customName') or hilink_info.get("name", f"HiLink Modem {gateway_ip}"),
                "interfaceName": interface_name,
                "status": modem_status,
                "ipAddress": modem_ip,
                "publicIpAddress": "N/A",
                "proxyStatus": proxy_status,
                "source": "hilink_webui",
                "proxyConfig": cfg,
                "serverLanIp": get_primary_lan_ip(),
                "details": {
                    "operator": hilink_info.get("operator"),
                    "network_mode": hilink_info.get("network_mode"),
                    "rssi": hilink_info.get("rssi"),
                    "rsrp": hilink_info.get("rsrp"),
                    "sinr": hilink_info.get("sinr"),
                    "rsrq": hilink_info.get("rsrq"),
                    "imei": hilink_info.get("imei"),
                }
            }
            all_modems_data.append(modem_data)
        except Exception as e:
            log_message("ERROR", f"Could not get status for modem at {gateway_ip}: {e}")
            # Add a placeholder so the user knows we tried
            all_modems_data.append({
                "id": f"error_{gateway_ip}",
                "name": f"Modem at {gateway_ip}",
                "interfaceName": f"error_{gateway_ip.replace('.', '_')}",
                "status": "error",
                "ipAddress": gateway_ip,
                "publicIpAddress": None,
                "proxyStatus": "error",
                "source": "hilink_webui",
                "proxyConfig": None,
                "serverLanIp": get_primary_lan_ip(),
                "details": {"error": str(e)}
            })

    return {"success": True, "data": all_modems_data}

# --- Action Dispatcher ---
def main():
    initialize_environment()
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "No action specified"}))
        sys.exit(1)

    action = sys.argv[1]
    args = sys.argv[2:]
    result = {}
    
    try:
        log_message("DEBUG", f"Backend action '{action}' called with args: {args}")
        
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

    