
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

# --- Configuration ---
STATE_DIR = Path(os.path.expanduser("~")) / ".proxy_pilot_state"
STATE_DIR.mkdir(exist_ok=True)
PROXY_CONFIGS_FILE = STATE_DIR / "proxy_configs.json"
TUNNEL_PIDS_FILE = STATE_DIR / "tunnel_pids.json"
LOG_FILE = STATE_DIR / "activity.log"
LOG_MAX_ENTRIES = 200
THREPROXY_CONFIG_DIR = Path("/etc/3proxy/conf")
PORT_RANGE_START = 30000
PORT_RANGE_END = 31000

# --- Logging Helper ---
def log_message(level, message):
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
    except Exception as e:
        sys.stderr.write(f"Logging failed: {e}\n")

# --- Helper Functions ---
def run_command(command_list, use_sudo=False, timeout=15):
    try:
        result = subprocess.run(
            command_list, check=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        log_message("ERROR", f"Command timed out: {' '.join(command_list)}")
        raise Exception(f"Command timed out: {' '.join(command_list)}")
    except subprocess.CalledProcessError as e:
        error_output = e.stderr.strip() if e.stderr else "No error output."
        log_message("ERROR", f"Command failed: {' '.join(command_list)}. Error: {error_output}")
        if "couldn't find bearer" in error_output.lower():
            return json.dumps({"bearer_error": True, "message": error_output})
        if "unable to read database" in error_output.lower():
             return json.dumps({"vnstat_error": "not_ready", "message": error_output})
        if "Unit 3proxy@" in error_output and "not found" in error_output:
            raise Exception(f"Systemd unit file '3proxy@.service' not found. Please check installation steps. Error: {error_output}")
        raise Exception(f"Command failed: {' '.join(command_list)}\nError: {error_output}")
    except FileNotFoundError:
        log_message("ERROR", f"Command not found: {command_list[0]}. Is it installed and in your PATH?")
        raise Exception(f"Command not found: {command_list[0]}. Is it installed and in your PATH?")

def run_and_parse_json(command_list, use_sudo=False, timeout=15):
    raw_output = run_command(command_list, use_sudo, timeout)
    if not raw_output:
        return {}
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        log_message("ERROR", f"Failed to parse JSON from command: {' '.join(command_list)}")
        raise Exception(f"Failed to parse JSON from command: {' '.join(command_list)}\nOutput: {raw_output}")

def read_state_file(file_path, default_value={}):
    if not file_path.exists():
        return default_value
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, FileNotFoundError):
        return default_value

def write_state_file(file_path, data):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def get_or_create_proxy_config(interface_name, all_configs):
    if interface_name in all_configs and 'port' in all_configs[interface_name]:
        return all_configs[interface_name], False
    used_ports = {config.get('port') for config in all_configs.values() if 'port' in config}
    new_port = PORT_RANGE_START
    while new_port in used_ports:
        new_port += 1
        if new_port > PORT_RANGE_END:
            raise Exception("No available ports in the specified range.")
    new_config = {"port": new_port, "username": "", "password": "", "type": "Proxy", "bindIp": None, "customName": None}
    log_message("INFO", f"Generated new proxy config for {interface_name} on port {new_port}.")
    return new_config, True

def generate_3proxy_config_content(config, ip_address):
    if not ip_address or not config.get('port'):
        return None
    is_authenticated = config.get('username') and config.get('password')
    auth_lines = ""
    if is_authenticated:
        auth_lines = f"users {config['username']}:CL:{config['password']}\nallow {config['username']}"
    # Use the local IP for both internal and external binding for simplicity and correctness
    return f"""daemon
nserver 8.8.8.8
nserver 8.8.4.4
nscache 65536
timeouts 1 5 30 60 180 1800 15 60
{auth_lines}
proxy -p{config['port']} -i{ip_address} -e{ip_address}
socks -p{config['port']} -i{ip_address} -e{ip_address}
"""

def write_3proxy_config_file(interface_name, ip_address):
    try:
        THREPROXY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        all_configs = read_state_file(PROXY_CONFIGS_FILE)
        interface_config = all_configs.get(interface_name)
        if not interface_config:
            raise Exception(f"No configuration found for {interface_name}")
        config_content = generate_3proxy_config_content(interface_config, ip_address)
        if not config_content:
            log_message("WARN", f"Could not generate config content for {interface_name}, likely missing IP. Skipping write.")
            return None
        config_file_path = THREPROXY_CONFIG_DIR / f"{interface_name}.cfg"
        with open(config_file_path, 'w') as f:
            f.write(config_content)
        log_message("DEBUG", f"Wrote proxy config for {interface_name} to {config_file_path}.")
        return str(config_file_path)
    except Exception as e:
        log_message("ERROR", f"Failed to write proxy config for {interface_name}: {e}")
        raise Exception(f"Failed to write proxy config for {interface_name}: {e}")

# --- Core Logic Functions ---
def is_command_available(command):
    return shutil.which(command) is not None

def get_proxy_status(interface_name):
    try:
        run_command(['systemctl', 'is-active', '--quiet', f"3proxy@{interface_name}.service"])
        return 'running'
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # This is the expected state for a stopped service, so it's not an error.
        return 'stopped'
    except Exception as e:
        log_message("WARN", f"Could not determine proxy status for {interface_name}: {e}")
        return 'error'
        
def get_public_ip(interface_name):
    """Fetches the public IP address via a specific interface."""
    if not is_command_available("curl"):
        log_message("WARN", f"curl is not installed. Cannot fetch public IP for {interface_name}.")
        return None
    try:
        # Using api.ipify.org as it's simple and reliable
        return run_command(['curl', '--interface', interface_name, '--connect-timeout', '5', 'https://api.ipify.org'], timeout=10)
    except Exception as e:
        log_message("WARN", f"Could not fetch public IP for {interface_name}. It may not be fully online. Error: {e}")
        return None

def get_modems_from_ip_addr():
    modems = {}
    if not is_command_available("ip"):
        log_message("WARN", "`ip` command not found. Cannot perform primary modem detection.")
        return modems

    try:
        output = run_command(['ip', '-j', 'addr'])
        interfaces = json.loads(output)
        modem_interface_pattern = re.compile(r'^(enx|usb|wwan|ppp)')
        excluded_pattern = re.compile(r'^(lo|eth|wlan|docker|veth|br-|cali|vxlan)')

        for iface in interfaces:
            ifname = iface.get('ifname', '')
            if modem_interface_pattern.match(ifname) and not excluded_pattern.match(ifname):
                ip_address = None
                for addr_info in iface.get('addr_info', []):
                    if addr_info.get('family') == 'inet':
                        ip_address = addr_info.get('local')
                        break
                
                is_connected = iface.get('operstate') == 'UP' and ip_address
                public_ip = get_public_ip(ifname) if is_connected else None
                
                modems[ifname] = {
                    "id": iface.get('address', ifname),
                    "name": f"Modem ({ifname})",
                    "interfaceName": ifname,
                    "status": 'connected' if is_connected else 'disconnected',
                    "ipAddress": ip_address,
                    "publicIpAddress": public_ip,
                    "proxyStatus": get_proxy_status(ifname),
                    "source": "ip_addr",
                }
    except Exception as e:
        log_message("ERROR", f"Error detecting modems from 'ip addr': {e}")
    return modems

def enhance_with_mmcli_data(modems_dict):
    if not is_command_available("mmcli"):
        log_message("INFO", "`mmcli` command not found. Skipping mmcli data enhancement.")
        return modems_dict

    try:
        modem_list_data = run_and_parse_json(['mmcli', '-L', '-J'], use_sudo=True)
        modem_paths = modem_list_data.get('modem-list', [])

        for modem_path in modem_paths:
            try:
                modem_details_data = run_and_parse_json(['mmcli', '-m', modem_path, '-J'], use_sudo=True)
                modem_info = modem_details_data.get('modem', {})
                interface_name = modem_info.get('generic', {}).get('primary-port')
                if interface_name and interface_name in modems_dict:
                    device_id = modem_info.get('generic', {}).get('device-identifier', interface_name)
                    modem_model = modem_info.get('3gpp', {}).get('imei', f'Modem ({device_id[-4:]})')
                    
                    # More descriptive name
                    vendor = modem_info.get('device-properties', {}).get('device.vendor.name', '')
                    model = modem_info.get('device-properties', {}).get('device.model', modem_model)

                    modems_dict[interface_name]['id'] = device_id
                    modems_dict[interface_name]['name'] = f"{vendor} {model}".strip() if vendor else model
                    modems_dict[interface_name]['source'] = "mmcli_enhanced"
            except Exception as e:
                log_message("WARN", f"Could not get details for modem {modem_path}. Error: {e}")
                continue
    except Exception as e:
        log_message("ERROR", f"Error in enhance_with_mmcli_data: {e}")
    return modems_dict

def get_all_modem_statuses():
    try:
        all_modems_dict = get_modems_from_ip_addr()
        all_modems_dict = enhance_with_mmcli_data(all_modems_dict)
        status_list = list(all_modems_dict.values())
        
        if not status_list:
            log_message("INFO", "No modems detected by any method.")
            return {"success": True, "data": []}

        proxy_configs = read_state_file(PROXY_CONFIGS_FILE)
        configs_changed = False

        for modem in status_list:
            interface_name = modem['interfaceName']
            # Step 1: Ensure config exists in state file
            modem_proxy_config, created = get_or_create_proxy_config(interface_name, proxy_configs)
            if created:
                proxy_configs[interface_name] = modem_proxy_config
                configs_changed = True

            # Step 2: Apply custom name if it exists
            if proxy_configs.get(interface_name, {}).get('customName'):
                 modem['name'] = proxy_configs[interface_name]['customName']
            
            # Step 3: Update bindIp in config if it differs
            current_bind_ip = proxy_configs.get(interface_name, {}).get('bindIp')
            if modem['ipAddress'] and current_bind_ip != modem['ipAddress']:
                 proxy_configs.setdefault(interface_name, {})['bindIp'] = modem['ipAddress']
                 configs_changed = True
            
            # Step 4: Proactively write the 3proxy config file to disk if modem is connected
            if modem['status'] == 'connected' and modem['ipAddress']:
                write_3proxy_config_file(interface_name, modem['ipAddress'])

        if configs_changed:
            write_state_file(PROXY_CONFIGS_FILE, proxy_configs)

        return {"success": True, "data": status_list}
    except Exception as e:
        log_message("ERROR", f"Error in get_all_modem_statuses: {e}")
        return {"success": False, "error": str(e)}

def proxy_action(action, interface_name):
    try:
        log_message("INFO", f"Attempting to {action} proxy for {interface_name}.")
        # No longer need to write config here, it's done proactively.
        # Just check if config file exists.
        config_file_path = THREPROXY_CONFIG_DIR / f"{interface_name}.cfg"
        if not config_file_path.exists() and action in ['start', 'restart']:
            # As a fallback, try to write it now.
            log_message("WARN", f"Proxy config for {interface_name} not found. Attempting to create it now.")
            statuses_result = get_all_modem_statuses()
            if not statuses_result['success']:
                raise Exception("Could not get modem statuses to write fallback config.")
            modem_status = next((m for m in statuses_result['data'] if m['interfaceName'] == interface_name), None)
            if not modem_status or not modem_status['ipAddress']:
                 raise Exception(f"Modem {interface_name} is not connected or has no IP address. Cannot {action} proxy.")
            write_3proxy_config_file(interface_name, modem_status['ipAddress'])

        service_name = f"3proxy@{interface_name}.service"
        run_command(['systemctl', action, service_name], use_sudo=True)
        log_message("INFO", f"Proxy action '{action}' successful for {interface_name}.")
        return {"success": True, "data": {"message": f"Proxy {action} successful for {interface_name}"}}
    except Exception as e:
        log_message("ERROR", f"Proxy action '{action}' for {interface_name} failed: {e}")
        return {"success": False, "error": str(e)}

def modem_action(action, interface_name, args_json):
    try:
        args = json.loads(args_json)
        log_message("INFO", f"Performing modem action '{action}' for {interface_name}.")
        if not is_command_available("mmcli"):
            raise Exception("`mmcli` command not found. This feature requires ModemManager to be installed.")

        modem_list_data = run_and_parse_json(['mmcli', '-L', '-J'], use_sudo=True)
        modem_mm_path = None
        for modem_path in modem_list_data.get('modem-list', []):
            try:
                modem_details_data = run_and_parse_json(['mmcli', '-m', modem_path, '-J'], use_sudo=True)
                if modem_details_data.get('modem', {}).get('generic', {}).get('primary-port') == interface_name:
                    modem_mm_path = modem_path
                    break
            except Exception: continue
        if not modem_mm_path:
            raise Exception(f"Could not find modem '{interface_name}' managed by ModemManager.")

        if action == 'send-sms':
            create_result = run_and_parse_json(['mmcli', '-m', modem_mm_path, f'--messaging-create-sms=text="{args["message"]}",number="{args["recipient"]}"', '-J'], use_sudo=True)
            sms_path = create_result.get('sms', {}).get('path')
            if not sms_path:
                raise Exception("Failed to create SMS.")
            run_command(['mmcli', '-s', sms_path, '--send'], use_sudo=True)
            run_command(['mmcli', '-m', modem_mm_path, f'--messaging-delete-sms={sms_path.split("/")[-1]}'], use_sudo=True)
            log_message("INFO", f"SMS sent to {args['recipient']} via {interface_name}.")
            return {"success": True, "data": {"message": "SMS sent successfully."}}
        elif action == 'read-sms':
            list_result = run_and_parse_json(['mmcli', '-m', modem_mm_path, '--messaging-list-sms', '-J'], use_sudo=True)
            sms_paths = list_result.get('modem', {}).get('messaging', {}).get('sms', [])
            messages = []
            for sms_path in sms_paths:
                sms_details_data = run_and_parse_json(['mmcli', '-s', sms_path, '-J'], use_sudo=True)
                sms_details = sms_details_data.get('sms', {})
                content = sms_details.get('content', {})
                messages.append({"id": sms_path.split('/')[-1], "from": content.get('number', 'Unknown'), "timestamp": sms_details.get('properties', {}).get('timestamp', ''), "content": content.get('text', '')})
            log_message("INFO", f"Read {len(messages)} SMS from {interface_name}.")
            return {"success": True, "data": messages}
        elif action == 'send-ussd':
            response_str = run_command(['mmcli', '-m', modem_mm_path, f'--3gpp-ussd-initiate={args["ussdCode"]}'], use_sudo=True)
            log_message("INFO", f"USSD '{args['ussdCode']}' sent via {interface_name}.")
            return {"success": True, "data": {"response": response_str}}
        return {"success": False, "error": "Unknown modem action"}
    except Exception as e:
        log_message("ERROR", f"Modem action '{action}' for {interface_name} failed: {e}")
        return {"success": False, "error": str(e)}

def rotate_ip(interface_name):
    try:
        log_message("INFO", f"Attempting IP rotation for {interface_name}.")
        if not is_command_available("mmcli"):
            raise Exception("`mmcli` is required for IP rotation.")

        statuses_result = get_all_modem_statuses()
        modem_to_rotate = next((m for m in statuses_result['data'] if m['interfaceName'] == interface_name), None)
        if not modem_to_rotate or 'mmcli' not in modem_to_rotate.get('source', ''):
            raise Exception(f"IP rotation is only supported for modems managed by ModemManager. {interface_name} is not one of them.")
        modem_id_or_path = modem_to_rotate['id']

        modem_list_data = run_and_parse_json(['mmcli', '-L', '-J'], use_sudo=True)
        modem_mm_path = None
        for m_path in modem_list_data.get('modem-list', []):
             modem_details_data = run_and_parse_json(['mmcli', '-m', m_path, '-J'], use_sudo=True)
             if modem_details_data.get('modem', {}).get('generic', {}).get('device-identifier') == modem_id_or_path:
                 modem_mm_path = m_path
                 break
        if not modem_mm_path:
            raise Exception(f"Could not find modem path for device ID {modem_id_or_path}")

        modem_details_data = run_and_parse_json(['mmcli', '-m', modem_mm_path, '-J'], use_sudo=True)
        bearer_path = modem_details_data.get('modem', {}).get('generic', {}).get('bearer')
        if not bearer_path or bearer_path == "/":
            run_command(['mmcli', '-m', modem_mm_path, '--simple-connect=any'], use_sudo=True)
        else:
            run_command(['mmcli', '-b', bearer_path, '--disconnect'], use_sudo=True, timeout=30)
            run_command(['sleep', '5'], timeout=10)
            run_command(['mmcli', '-m', modem_mm_path, '--simple-connect=any'], use_sudo=True, timeout=45)
        run_command(['sleep', '5'], timeout=10)
        
        restart_result = proxy_action('restart', interface_name)
        if not restart_result['success']:
             raise Exception(f"IP rotation seems successful, but failed to restart proxy: {restart_result['error']}")

        final_statuses = get_all_modem_statuses()
        final_modem = next((m for m in final_statuses.get('data', []) if m['interfaceName'] == interface_name), None)
        new_ip = final_modem.get('publicIpAddress', 'unknown') if final_modem else 'unknown'

        log_message("INFO", f"IP rotated for {interface_name}. New IP: {new_ip}.")
        return {"success": True, "data": {"message": f"IP rotated for {interface_name}, new IP is {new_ip}.", "newIp": new_ip}}
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
    except OSError: return False
    else: return True

def start_tunnel(tunnel_id, local_port, linked_to, tunnel_type, cloudflare_id=None):
    pids = get_tunnel_pids()
    if tunnel_id in pids and is_pid_running(pids[tunnel_id].get('pid')):
        log_message("INFO", f"Tunnel {tunnel_id} is already running.")
        return {"success": True, "message": "Tunnel already running."}
    
    if tunnel_type == "Ngrok":
        if not is_command_available("ngrok"): raise Exception("`ngrok` command not found.")
        process = subprocess.Popen(['ngrok', 'tcp', str(local_port), '--log=stdout'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, preexec_fn=os.setsid)
        run_command(['sleep', '2'], timeout=5)
        try:
            api_output = run_command(['curl', '-s', 'http://127.0.0.1:4040/api/tunnels'])
            api_data = json.loads(api_output)
            tunnel_info = next((t for t in api_data.get('tunnels', []) if t.get('proto') == 'tcp' and str(t.get('config', {}).get('addr')).endswith(str(local_port))), None)
            if not tunnel_info:
                process.terminate()
                raise Exception("Could not find started ngrok tunnel in ngrok API.")
            url = tunnel_info.get('public_url')
        except Exception as e:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            raise e
    elif tunnel_type == "Cloudflare":
        if not is_command_available("cloudflared"): raise Exception("`cloudflared` command not found.")
        if not cloudflare_id: raise Exception("Cloudflare Tunnel ID is required.")
        url = f"tcp://{cloudflare_id}.trycloudflare.com" # This is just a guess, real URL may vary
        command = ['cloudflared', 'tunnel', 'run', '--url', f'tcp://localhost:{local_port}', cloudflare_id]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, preexec_fn=os.setsid)
        run_command(['sleep', '2'], timeout=5)
    else:
        raise Exception(f"Unknown tunnel type: {tunnel_type}")

    pids[tunnel_id] = {"pid": process.pid, "port": local_port, "url": url, "type": tunnel_type, "linkedTo": linked_to}
    save_tunnel_pids(pids)
    log_message("INFO", f"Started {tunnel_type} tunnel {tunnel_id} for port {local_port} with PID {process.pid}. URL: {url}")
    return {"success": True, "data": pids[tunnel_id]}

def stop_tunnel(tunnel_id):
    pids = get_tunnel_pids()
    tunnel_info = pids.get(tunnel_id)
    if not tunnel_info or not is_pid_running(tunnel_info.get('pid')):
        log_message("INFO", f"Tunnel {tunnel_id} not running.")
        if tunnel_id in pids: del pids[tunnel_id]; save_tunnel_pids(pids)
        return {"success": True, "message": "Tunnel was not running."}
    pid = tunnel_info.get('pid')
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        log_message("INFO", f"Stopped tunnel {tunnel_id} with PID {pid}.")
    except OSError as e:
        log_message("WARN", f"Could not kill process group {pid} for {tunnel_id}: {e}.")
    del pids[tunnel_id]
    save_tunnel_pids(pids)
    return {"success": True, "message": "Tunnel stopped."}

def get_all_tunnel_statuses():
    pids = get_tunnel_pids()
    statuses = []
    pids_changed = False
    for tunnel_id, info in list(pids.items()):
        if is_pid_running(info.get('pid')):
            statuses.append({"id": tunnel_id, "type": info.get("type", "Unknown"), "status": "active", "url": info.get("url"), "localPort": info.get("port"), "linkedTo": info.get("linkedTo")})
        else:
            log_message("INFO", f"Tunnel {tunnel_id} with PID {info.get('pid')} is no longer running. Cleaning up.")
            del pids[tunnel_id]
            pids_changed = True
    if pids_changed: save_tunnel_pids(pids)
    return {"success": True, "data": statuses}

def get_available_cloudflare_tunnels():
    if not is_command_available("cloudflared"): return {"success": True, "data": []}
    cf_dir = Path(os.path.expanduser("~")) / ".cloudflared"
    tunnels = []
    if cf_dir.exists():
        for cert_file in cf_dir.glob("*.pem"):
            tunnel_id = cert_file.stem
            tunnels.append({"id": tunnel_id, "name": f"Cloudflare Tunnel ({tunnel_id[:8]}...)"})
    return {"success": True, "data": tunnels}

# --- vnstat Functions ---
def get_vnstat_interfaces():
    if not is_command_available("vnstat"): raise Exception("`vnstat` is not installed.")
    try:
        output = run_command(['vnstat', '--iflist'])
        return {"success": True, "data": output.split()}
    except Exception as e:
        log_message("ERROR", f"Failed to get vnstat interface list: {e}")
        return {"success": False, "error": str(e)}

def get_vnstat_stats(interface_name):
    if not is_command_available("vnstat"): raise Exception("`vnstat` is not installed.")
    try:
        daily_data = run_and_parse_json(['vnstat', '-i', interface_name, '-d', '-J'])
        monthly_data = run_and_parse_json(['vnstat', '-i', interface_name, '-m', '-J'])
        hourly_data = run_and_parse_json(['vnstat', '-i', interface_name, '-h', '-j'])
        interface_stats = daily_data['interfaces'][0]
        combined_stats = {"name": interface_stats.get('name', interface_name), "totalrx": interface_stats.get('traffic', {}).get('total', {}).get('rx', 0), "totaltx": interface_stats.get('traffic', {}).get('total', {}).get('tx', 0), "day": interface_stats.get('traffic', {}).get('day', []), "month": monthly_data['interfaces'][0].get('traffic', {}).get('month', []), "hour": hourly_data['interfaces'][0].get('traffic', {}).get('hour', [])}
        return {"success": True, "data": combined_stats}
    except Exception as e:
        log_message("ERROR", f"Failed to get vnstat stats for {interface_name}: {e}")
        return {"success": False, "error": str(e)}

# --- System & Config Functions ---
def get_logs():
    try:
        if not LOG_FILE.exists(): return {"success": True, "data": []}
        with open(LOG_FILE, 'r') as f: lines = f.readlines()
        log_entries = [json.loads(line.strip()) for line in lines if line.strip()]
        return {"success": True, "data": log_entries}
    except Exception as e:
        return {"success": False, "error": f"Failed to read log file: {e}"}

def get_all_configs():
    try:
        configs = read_state_file(PROXY_CONFIGS_FILE)
        return {"success": True, "data": configs}
    except Exception as e:
        log_message("ERROR", f"Failed to read proxy configs file: {e}")
        return {"success": False, "error": f"Failed to read proxy configs file: {e}"}

def update_proxy_config(interface_name, updates_json):
    try:
        updates = json.loads(updates_json)
        all_configs = read_state_file(PROXY_CONFIGS_FILE)
        if interface_name not in all_configs: all_configs[interface_name] = {}
        is_credential_update = 'username' in updates or 'password' in updates
        for key, value in updates.items():
            all_configs[interface_name][key] = value
        write_state_file(PROXY_CONFIGS_FILE, all_configs)
        log_message("INFO", f"Updated config for {interface_name} with: {updates}")
        if is_credential_update and get_proxy_status(interface_name) == 'running':
            log_message("INFO", f"Credentials changed for {interface_name}. Restarting proxy.")
            proxy_action('restart', interface_name)
        return {"success": True, "data": all_configs[interface_name]}
    except Exception as e:
        log_message("ERROR", f"Failed to update config for {interface_name}: {e}")
        return {"success": False, "error": str(e)}

# --- Main Execution Block ---
def main():
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
        log_message("ERROR", f"An unexpected error occurred in main for action '{action}': {e}")
        result = {"success": False, "error": str(e)}

    print(json.dumps(result))

if __name__ == "__main__":
    main()

    