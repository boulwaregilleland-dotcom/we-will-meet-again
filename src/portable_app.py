"""ECJTU Campus Connect 2.0; credentials protected by Windows DPAPI.

Protocol reference: https://github.com/bestxiangest/ECJTUCampusNetwork-AutoLogin
Independent implementation using only the Python standard library.
"""
import ctypes
from ctypes import wintypes
import http.client
import ipaddress
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import shutil
import hashlib
import threading
import queue
from urllib.parse import urlencode, urlsplit, urljoin, parse_qs

FROZEN = bool(getattr(sys, 'frozen', False))
ROOT = Path(os.environ['LOCALAPPDATA']) / 'ECJTUAutoLogin'
CONFIG = ROOT / 'credentials.dpapi'
STATE = ROOT / 'status.json'
PORTAL = '172.16.2.100'
PYTHONW = Path(sys.executable).with_name('pythonw.exe')
STARTUP = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/Startup/ECJTU AutoLogin.lnk'
CREATE_NO_WINDOW = 0x08000000
SERVICES = {
    'campus': ('学校免费网', '工位网 · 学号和密码', ''),
    'telecom': ('中国电信', '电信校园宽带', '@telecom'),
    'mobile': ('中国移动', '移动校园宽带', '@cmcc'),
    'unicom': ('中国联通', '联通校园宽带', '@unicom'),
}
MUTEX_NAME = 'Local\\ECJTU_Wired_Telecom_AutoLogin'  # Keep v1 compatibility.


def account_for_service(username, service):
    if service not in SERVICES:
        raise ValueError('请选择一种网络服务。')
    name = username.strip()
    for _, _, suffix in SERVICES.values():
        if suffix and name.lower().endswith(suffix):
            name = name[:-len(suffix)]
            break
    if not name or '@' in name or ',' in name or any(c.isspace() for c in name):
        raise ValueError('请填写学号或校园网账号，不要输入空格、逗号或未知运营商后缀。')
    return name + SERVICES[service][2]


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, decrypt=False):
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    func = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    func.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    func.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buf = ctypes.create_string_buffer(data)
    src = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    dst = Blob()
    if not func(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(dst.data, dst.size)
    finally:
        kernel.LocalFree(dst.data)


def powershell(code):
    shell = str(Path(os.environ['SYSTEMROOT']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command',
                             "[Console]::OutputEncoding=[Text.UTF8Encoding]::new();" + code],
                            capture_output=True, encoding='utf-8', timeout=25,
                            creationflags=CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('Windows configuration command failed')
    return result.stdout.strip()


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def install_startup(enabled=True):
    if FROZEN:
        source = Path(sys.executable)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
        folder = Path(os.environ['LOCALAPPDATA']) / 'Programs' / 'ECJTUAutoLogin'
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / ('ECJTUAutoLogin-' + digest + '.exe')
        if not target.exists():
            shutil.copy2(source, target)
        command = [str(target), '--worker']
    else:
        target = PYTHONW
        command = [str(target), str(Path(__file__).resolve()), '--worker']
    if not enabled:
        STARTUP.unlink(missing_ok=True)
        return command
    code = "$ErrorActionPreference='Stop';$w=New-Object -ComObject WScript.Shell;"
    code += '$s=$w.CreateShortcut(' + ps_quote(STARTUP) + ');'
    code += '$s.TargetPath=' + ps_quote(target) + ';'
    code += '$s.Arguments=' + ps_quote(subprocess.list2cmdline(command[1:])) + ';'
    code += '$s.WorkingDirectory=' + ps_quote(ROOT) + ';$s.WindowStyle=7;$s.Save()'
    powershell(code)
    return command


def wired_ip_legacy():
    code = "$a=Get-NetAdapter -Physical | Where-Object {$_.Status -eq 'Up' -and $_.MediaType -eq '802.3'};"
    code += "foreach($n in $a){Get-NetIPAddress -InterfaceIndex $n.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {$_.AddressState -eq 'Preferred' -and $_.IPAddress -notlike '169.254.*'} | Select-Object -ExpandProperty IPAddress}"
    for value in powershell(code).splitlines():
        try:
            addr = ipaddress.ip_address(value.strip())
            if addr.version == 4 and not addr.is_loopback and not addr.is_link_local:
                return str(addr)
        except ValueError:
            pass
    return None


def wifi_connections(output):
    """Read stable GUID/SSID fields, independent of translated interface names."""
    matches = list(re.finditer(r'(?im)^\s*GUID\s*:\s*([0-9a-f-]{36})\s*$', output))
    result = []
    for i, match in enumerate(matches):
        block = output[match.end():matches[i+1].start() if i+1 < len(matches) else len(output)]
        ssid = re.search(r'(?im)^\s*SSID\s*:\s*(.*?)\s*$', block)
        if ssid:
            result.append((match.group(1), ssid.group(1)))
    return result


def wireless_ip_legacy():
    output = powershell('& "$env:SystemRoot\\System32\\netsh.exe" wlan show interfaces')
    for guid, ssid in wifi_connections(output):
        if ssid != 'ECJTU-Stu':
            continue
        code = "$a=Get-NetAdapter -Physical | Where-Object {[guid]$_.InterfaceGuid -eq [guid]" + ps_quote(guid) + " -and $_.Status -eq 'Up'};"
        code += "foreach($n in $a){Get-NetIPAddress -InterfaceIndex $n.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {$_.AddressState -eq 'Preferred'} | Select-Object -ExpandProperty IPAddress}"
        for value in powershell(code).splitlines():
            try:
                addr = ipaddress.ip_address(value.strip())
                if addr.version == 4 and not addr.is_loopback and not addr.is_link_local and not addr.is_unspecified:
                    return str(addr)
            except ValueError:
                pass
    return None


_hardware_cache = (None, set())

def fast_adapters():
    global _hardware_cache
    from native_adapters import snapshot
    rows = snapshot()
    signature = frozenset(row['guid'] for row in rows)
    if signature != _hardware_cache[0]:
        guids = powershell('Get-NetAdapter -Physical | Select-Object -ExpandProperty InterfaceGuid')
        _hardware_cache = (signature, {g.strip().strip('{}').lower() for g in guids.splitlines()})
    return [row for row in rows if row['guid'] in _hardware_cache[1] and row['up'] and row['ips']]


def wired_ip():
    try:
        return next((row['ips'][0] for row in fast_adapters() if row['kind'] == 6), None)
    except OSError:
        return wired_ip_legacy()


def wireless_ip():
    try:
        rows = [r for r in fast_adapters() if r['kind'] == 71]
        if not rows:
            return None
        command = str(Path(os.environ['SYSTEMROOT']) / 'System32/netsh.exe')
        result = subprocess.run([command,'wlan','show','interfaces'],capture_output=True,
                                timeout=3,creationflags=CREATE_NO_WINDOW)
        # GUID and the official SSID are ASCII in every Windows display language.
        connected = {g.lower() for g,s in wifi_connections(result.stdout.decode('ascii','replace')) if s == 'ECJTU-Stu'}
        return next((r['ips'][0] for r in rows if r['guid'] in connected), None)
    except (OSError, subprocess.TimeoutExpired):
        return wireless_ip_legacy()


def saved_profiles(cfg):
    """Migrate legacy credentials into their original service only."""
    profiles = {k: dict(v) for k, v in cfg.get('profiles', {}).items() if isinstance(v, dict)}
    if cfg.get('username') and cfg.get('password'):
        key = cfg.get('transport', 'wired') + ':' + cfg.get('service', 'telecom')
        profiles.setdefault(key, dict(username=cfg['username'], password=cfg['password']))
    return profiles


def wired_services(cfg):
    profiles = saved_profiles(cfg)
    result = ['campus'] if profiles.get('wired:campus', {}).get('password') else []
    operators = [s for s in ('telecom','mobile','unicom') if profiles.get('wired:'+s, {}).get('password')]
    selected = cfg.get('wired_operator') or cfg.get('preferred_services', {}).get('wired')
    if selected not in operators:
        selected = cfg.get('service') if cfg.get('service') in operators else (operators[0] if len(operators)==1 else None)
    if selected:
        result.append(selected)
    return result


def connection_for_config(cfg):
    profiles = saved_profiles(cfg)
    preferred = cfg.get('transport', 'wired')
    choices = [preferred, 'wired' if preferred == 'wireless' else 'wireless']
    missing = False
    for transport in choices:
        ip = wireless_ip() if transport == 'wireless' else wired_ip()
        if not ip:
            continue
        service = cfg.get('preferred_services', {}).get(transport)
        if transport == 'wired':
            available = wired_services(cfg)
            service = available[0] if available else service
        if not service and transport == preferred:
            service = cfg.get('service', 'telecom')
        candidates = [key.split(':', 1)[1] for key in profiles if key.startswith(transport + ':')]
        if not service and len(candidates) == 1:
            service = candidates[0]
        profile = profiles.get(transport + ':' + str(service), {})
        if not profile.get('username') or not profile.get('password'):
            missing = True
            continue
        effective = dict(cfg, **profile)
        effective.update(transport=transport, service=service)
        return ip, effective, None
    return None, cfg, 'profile_required' if missing else 'waiting_for_network'


def request(ip, host, path, port=80, body=None, headers=None, metadata=False, timeout=7):
    # Direct connection bound to the selected adapter IPv4, without proxies.
    conn = http.client.HTTPConnection(host, port, timeout=timeout, source_address=(ip, 0))
    try:
        conn.request('POST' if body is not None else 'GET', path, body=body, headers=headers or {})
        res = conn.getresponse()
        text = res.read(131072).decode('utf-8', 'replace')
        if metadata:
            return res.status, text, {key.lower(): value for key, value in res.getheaders()}
        return res.status, text
    finally:
        conn.close()


PROBE_SLOTS = threading.BoundedSemaphore(4)


def online(ip):
    probes = [('www.msftconnecttest.com', '/connecttest.txt', 'Microsoft Connect Test'),
              ('detectportal.firefox.com', '/success.txt', 'success')]
    results = queue.Queue()
    def probe(host, path, expected):
        if not PROBE_SLOTS.acquire(blocking=False):
            results.put(False)
            return
        try:
            status, text = request(ip, host, path, timeout=2)
            results.put(status == 200 and text.strip() == expected)
        except Exception:
            results.put(False)
        finally:
            PROBE_SLOTS.release()
    for args in probes:
        threading.Thread(target=probe, args=args, daemon=True).start()
    deadline = time.monotonic() + 2.5
    for _ in probes:
        try:
            if results.get(timeout=max(0, deadline-time.monotonic())):
                return True
        except queue.Empty:
            break
    return False


def portal_context(ip):
    # Shared controller values from the user's student/workstation portal URLs.
    # Client IPv4 always comes from the currently connected network interface.
    query = {'wlanacip': '172.16.1.2', 'wlanacname': 'ecjtu_nic_ME60', 'vlanid': '0'}
    path = '/'
    for attempt in range(4):
        status, page, headers = request(ip, PORTAL, path, metadata=True)
        location = headers.get('location', '') if status in (301, 302, 303, 307, 308) else ''
        if not location and status == 200:
            match = re.search(r'(?:location(?:\.href)?\s*=\s*|location\.(?:replace|assign)\s*\(\s*)[\"\x27]([^\"\x27]+)', page, re.I)
            if match:
                location = match.group(1)
        if location:
            parsed = urlsplit(urljoin('http://' + PORTAL + path, location))
            if parsed.scheme != 'http' or parsed.hostname != PORTAL or parsed.port not in (None, 80):
                return 0, '', query
            values = parse_qs(parsed.query)
            for key in ('wlanacip', 'wlanacname', 'vlanid'):
                if values.get(key):
                    query[key] = values[key][0][:96]
            # Replace stale client address parameters before loading the page.
            values['wlanuserip'] = [ip]
            values['ip'] = [ip]
            path = (parsed.path or '/') + '?' + urlencode(values, doseq=True)
            continue
        if status == 200 and re.search(r'drcom|eportal|DDDDD|华东交通', page, re.I):
            query['referer'] = 'http://' + PORTAL + path
            return status, page, query
        if attempt == 0:
            path = '/a70.htm?' + urlencode(dict(query, wlanuserip=ip, ip=ip))
            continue
        return status, page, query
    return 0, '', query


def login(ip, cfg):
    status, page, portal = portal_context(ip)
    # Check for a campus authentication page before sending any credentials.
    if status != 200 or not re.search(r'drcom|eportal|DDDDD|[华]东交通', page, re.I):
        return 'portal_unavailable'
    params = dict(c='ACSetting', a='Login', protocol='http:', hostname=PORTAL,
                  iTermType='1', wlanuserip=ip, wlanacip=portal['wlanacip'], wlanacname=portal['wlanacname'],
                  mac='00-00-00-00-00-00', ip=ip, enAdvert='0', queryACIP='0', loginMethod='1')
    username = account_for_service(cfg['username'], cfg.get('service', 'telecom'))
    form = dict(DDDDD=',0,' + username, upass=cfg['password'], R1='0', R2='0', R3='0',
                R6='0', para='00', **{'0MKKey': '123456'}, buttonClicked='', redirect_url='',
                err_flag='', username='', password='', user='', cmd='', Login='')
    headers = {'Content-Type': 'application/x-www-form-urlencoded',
               'Origin': 'http://' + PORTAL, 'Referer': portal.get('referer', 'http://' + PORTAL + '/a70.htm'),
               'User-Agent': 'Mozilla/5.0'}
    _, reply = request(ip, PORTAL, '/eportal/?' + urlencode(params), port=801,
                       body=urlencode(form).encode('ascii'), headers=headers)
    if re.search(r'密码错误|账号或密码错误|用户名或密码错误|password.{0,12}(error|incorrect)', reply, re.I):
        return 'credentials_rejected'
    if online(ip):
        return 'online'
    if cfg.get('_quick_validation'):
        return 'authentication_unverified'
    for pause in (.5, 1):
        time.sleep(pause)
        if online(ip):
            return 'online'
    return 'authentication_unverified'


_rejected_profiles = set()

def login_connection(ip, cfg):
    if cfg.get('transport') != 'wired':
        return login(ip, cfg)
    profiles = saved_profiles(cfg)
    services = wired_services(cfg)
    if not services:
        return 'profile_required'
    outcome = 'credentials_rejected'
    for index, service in enumerate(services):
        profile = profiles['wired:'+service]
        identity = (ip, service, profile['username'])
        if identity in _rejected_profiles:
            continue
        logging.info('wired_attempt_%s', service)
        started = time.monotonic()
        outcome = login(ip, dict(cfg, **profile, _quick_validation=index < len(services)-1, service=service))
        logging.info('wired_result_%s_%s elapsed_ms=%d', service, outcome, (time.monotonic()-started)*1000)
        if outcome == 'credentials_rejected':
            _rejected_profiles.add(identity)
        if outcome in ('online','portal_unavailable'):
            return outcome
    return outcome


LABELS = {
    'profile_required': '已检测到网络，请先为该连接方式选择服务并保存账号',
    'waiting_for_network': '等待校园网网线或 ECJTU-Stu',
    'waiting_for_cable': '等待校园网网线接通',
    'waiting_for_wifi': '请连接 ECJTU-Stu，并在 Windows 勾选自动连接',
    'online': '当前网络已联网',
    'trying': '正在认证，请稍候',
    'portal_unavailable': '未检测到校园网认证页面，等待重试',
    'authentication_unverified': '尚未确认认证成功，稍后重试',
    'credentials_rejected': '账号或密码被拒绝，请修改配置',
    'retry_limit': '连续认证未成功，暂停提交账号；请修改配置后重试',
    'network_unavailable': '网络暂时不可达，等待重试',
    'config_error': '无法读取账号配置，请重新保存',
    'disabled': '已停止自动认证',
    'completed': '本次认证完成 · 已关闭断线重连',
}


def set_state(code):
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps({'state': code, 'time': time.strftime('%Y-%m-%d %H:%M:%S'),
                               'epoch': time.time(), 'version': 3}, ensure_ascii=False), encoding='utf-8')
    tmp.replace(STATE)
    if getattr(set_state, 'previous', None) != code:
        logging.info(code)
        set_state.previous = code


def worker_running():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenMutexW(0x00100000, False, MUTEX_NAME)
    if handle:
        kernel.CloseHandle(handle)
        return True
    return False


def stop_worker():
    # v1 also exits when the credential file disappears. Keep only encrypted bytes.
    backup = CONFIG.read_bytes() if CONFIG.exists() else None
    CONFIG.unlink(missing_ok=True)
    for _ in range(400):
        if not worker_running():
            return
        time.sleep(0.2)
    if backup:
        CONFIG.write_bytes(backup)
    raise RuntimeError('后台仍在结束网络请求，请稍后重试或重新登录 Windows。')


def save_configuration(cfg):
    ROOT.mkdir(parents=True, exist_ok=True)
    content = protect(json.dumps(cfg).encode('utf-8'))
    command = install_startup(cfg.get('autostart', True))
    stop_worker()
    temp = CONFIG.with_suffix('.tmp')
    temp.write_bytes(content)
    temp.replace(CONFIG)
    STATE.unlink(missing_ok=True)
    subprocess.Popen(command, creationflags=CREATE_NO_WINDOW)


def worker():
    ROOT.mkdir(parents=True, exist_ok=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    mutex = kernel.CreateMutexW(None, False, MUTEX_NAME)
    if not mutex or ctypes.get_last_error() == 183:
        if mutex:
            kernel.CloseHandle(mutex)
        return
    try:
        from network_events import NetworkEvents
        watcher = None
        try:
            watcher = NetworkEvents()
        except OSError:
            logging.warning('network_events_unavailable_using_timed_fallback')
        try:
            worker_loop(watcher)
        finally:
            if watcher:
                watcher.close()
    finally:
        kernel.CloseHandle(mutex)


def notify_success():
    command = [sys.executable, '--notify-success'] if FROZEN else [sys.executable, str(Path(__file__).resolve()), '--notify-success']
    try:
        subprocess.Popen(command, creationflags=CREATE_NO_WINDOW)
    except OSError:
        logging.warning('success_notice_unavailable')


def worker_loop(watcher=None):
    handler = RotatingFileHandler(ROOT / 'autologin.log', maxBytes=262144, backupCount=2, encoding='utf-8')
    logging.basicConfig(handlers=[handler], level=logging.INFO, format='%(asctime)s %(message)s')
    version = None
    cfg = None
    failures = 0
    paused = None
    connected_ip = None
    active_key = None
    retry_states = {}
    next_attempt = 0
    while CONFIG.exists():
        delay = 30
        if watcher:
            watcher.event.clear()
        try:
            stamp = CONFIG.stat().st_mtime_ns
            if stamp != version:
                cfg = json.loads(protect(CONFIG.read_bytes(), decrypt=True))
                version, failures, paused = stamp, 0, None
            ip, effective, waiting = connection_for_config(cfg)
            key = (effective.get('transport', 'wired'), effective.get('service', 'telecom'), ip)
            if key != active_key:
                active_key = key
                failures, paused, next_attempt = retry_states.get(key, (0, None, 0))
            if not ip:
                connected_ip = None
                set_state(waiting)
                delay = 300
                if watcher and time.monotonic() < watcher.settling_until:
                    delay = 1
            elif online(ip):
                set_state('online')
                if connected_ip != key:
                    notify_success()
                    connected_ip = key
                if not cfg.get('reconnect', True):
                    set_state('completed')
                    return
                failures, paused = 0, None
                next_attempt = 0
                delay = 300
            elif paused:
                connected_ip = None
                set_state(paused)
                delay = 300
            elif time.monotonic() < next_attempt:
                connected_ip = None
                set_state('authentication_unverified')
                delay = max(1, int(next_attempt - time.monotonic()))
            else:
                connected_ip = None
                set_state('trying')
                outcome = login_connection(ip, effective)
                set_state(outcome)
                if outcome == 'online':
                    notify_success()
                    connected_ip = key
                    if not cfg.get('reconnect', True):
                        set_state('completed')
                        return
                    failures = 0
                    delay = 300
                elif outcome == 'credentials_rejected':
                    paused = outcome
                elif outcome == 'authentication_unverified':
                    failures += 1
                    delay = min(30 * 2 ** failures, 600)
                    if failures >= 5:
                        paused = 'retry_limit'
                        set_state(paused)
                next_attempt = 0 if outcome == 'online' else time.monotonic() + delay
            retry_states[key] = (failures, paused, next_attempt)
        except (OSError, http.client.HTTPException):
            set_state('network_unavailable')
            delay = 60
        except Exception:
            set_state('config_error')
            delay = 60
        # Native changes wake immediately. Stable networks get a five-minute
        # health check; authentication failures retain their backoff timers.
        if watcher:
            watcher.wait(delay, CONFIG, version)
            continue
        # Registration fallback: no more frequent than the existing retry timer.
        for _ in range(min(delay, 60)):
            time.sleep(1)
            if not CONFIG.exists() or CONFIG.stat().st_mtime_ns != version:
                break
    set_state('disabled')


def setup():
    from connect_ui import ConnectUI
    ConnectUI(sys.modules[__name__], preview='--preview' in sys.argv).run()


def self_test(destination):
    """Explicit offline smoke test; no credential files or startup entries written."""
    from connect_ui import ConnectUI
    result = {'frozen': FROZEN, 'python': sys.version.split()[0]}
    try:
        interface = ConnectUI(sys.modules[__name__], preview=True)
        window = interface.root
        window.withdraw()
        window.update()
        for key in SERVICES:
            interface.select_service(key)
            assert interface.service.get() == key
        window.destroy()
        result['tkinter'] = True
        sample = b'fictional-offline-smoke-test'
        encrypted = protect(sample)
        result['dpapi'] = protect(encrypted, decrypt=True) == sample and sample not in encrypted
        result['powershell'] = powershell("Write-Output 'OK'") == 'OK'
        address = wired_ip()
        result['wired_probe'] = address is None or ipaddress.ip_address(address).version == 4
        address = wireless_ip()
        result['wireless_probe'] = address is None or ipaddress.ip_address(address).version == 4
        from network_events import NetworkEvents
        watcher = NetworkEvents(initial=True)
        try:
            result['network_events'] = len(watcher.handles) == 2 and watcher.event.wait(3)
        finally:
            watcher.close()
        result['passed'] = all(result[x] for x in ['frozen', 'tkinter', 'dpapi', 'powershell', 'wired_probe', 'wireless_probe', 'network_events'])
    except Exception as exc:
        result['passed'] = False
        result['error'] = type(exc).__name__
    Path(destination).write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    if '--self-test' in sys.argv:
        self_test(sys.argv[sys.argv.index('--self-test') + 1])
    elif '--worker' in sys.argv:
        worker()
    elif '--notify-success' in sys.argv:
        from success_notice import run
        run(sys.modules[__name__])
    else:
        setup()
