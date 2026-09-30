"""Windows IP Helper notifications; no network polling thread or external process."""
import ctypes
from ctypes import wintypes
import threading
import time


class NetworkEvents:
    def __init__(self, initial=False):
        self.event = threading.Event()
        self.settling_until = 0
        self.handles = []
        self.callbacks = []
        self.api = ctypes.WinDLL('iphlpapi')
        self.api.CancelMibChangeNotify2.argtypes = [wintypes.HANDLE]
        self.api.CancelMibChangeNotify2.restype = wintypes.ULONG
        callback_type = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)
        try:
            for name in ('NotifyIpInterfaceChange', 'NotifyUnicastIpAddressChange'):
                callback = callback_type(lambda context, row, kind: self.event.set())
                self.callbacks.append(callback)
                register = getattr(self.api, name)
                register.argtypes = [ctypes.c_ushort, callback_type, ctypes.c_void_p, ctypes.c_ubyte,
                                     ctypes.POINTER(wintypes.HANDLE)]
                register.restype = wintypes.ULONG
                handle = wintypes.HANDLE()
                result = register(0, callback, None, initial, ctypes.byref(handle))
                if result:
                    raise ctypes.WinError(result)
                self.handles.append(handle)
        except Exception:
            self.close()
            raise

    def close(self):
        # Cancellation must occur outside the notification callback.
        for handle in self.handles:
            self.api.CancelMibChangeNotify2(handle)
        self.handles.clear()

    def wait(self, seconds, config, version):
        from native_adapters import snapshot
        def fingerprint():
            try:
                return tuple((r['guid'],r['up'],tuple(r['ips'])) for r in snapshot() if r['kind'] in (6,71))
            except OSError:
                return None
        baseline = fingerprint()
        deadline = time.monotonic() + seconds
        while config.exists() and config.stat().st_mtime_ns == version:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return 'timeout'
            if self.event.wait(min(1, remaining)):
                self.settling_until = time.monotonic() + 12
                # Coalesce adapter/address notifications from the same transition.
                time.sleep(.15)
                return 'network'
            current = fingerprint()
            if baseline is not None and current is not None and current != baseline:
                self.settling_until = time.monotonic() + 12
                return 'network'
        return 'config'
