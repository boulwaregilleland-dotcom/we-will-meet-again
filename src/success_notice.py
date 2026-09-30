"""Independent success dialog: the network monitor never waits for the OK button."""
import json
import subprocess
import time
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox


def close_portal_once(app, dry_run=False):
    script = Path(__file__).with_name('close_portal.ps1')
    shell = Path(app.os.environ['SYSTEMROOT']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    command = [str(shell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script)]
    if dry_run:
        command.append('-DryRun')
    result = subprocess.run(command, capture_output=True, encoding='utf-8', timeout=8,
                            creationflags=app.CREATE_NO_WINDOW)
    if result.returncode:
        return {'closed': 0, 'errors': 1}
    return json.loads(result.stdout.strip())


def cleanup(app):
    # Allow the automatic browser window time to appear after authentication.
    for attempt in range(4):
        try:
            result = close_portal_once(app)
            app.ROOT.mkdir(parents=True, exist_ok=True)
            (app.ROOT/'browser-cleanup.json').write_text(json.dumps(dict(result,attempt=attempt+1,epoch=time.time())),encoding='utf-8')
            if result.get('closed', 0):
                break
        except (OSError, ValueError, subprocess.TimeoutExpired):
            break
        if attempt < 3:
            time.sleep(2)


def run(app):
    # Browser discovery must never delay the already-verified success message.
    threading.Thread(target=cleanup, args=(app,), daemon=False).start()
    kernel = app.ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [app.ctypes.c_void_p, app.wintypes.BOOL, app.wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = app.wintypes.HANDLE
    kernel.CloseHandle.argtypes = [app.wintypes.HANDLE]
    mutex = kernel.CreateMutexW(None, False, 'Local\\ECJTU_Success_Notice')
    if not mutex or app.ctypes.get_last_error() == 183:
        if mutex:
            kernel.CloseHandle(mutex)
        return
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        try:
            root.iconbitmap(str(Path(__file__).with_name('connect.ico')))
        except tk.TclError:
            pass
        messagebox.showinfo('我们将会再见', '网络验证成功\n现在可以正常上网了。', parent=root)
        root.destroy()
    finally:
        kernel.CloseHandle(mutex)
