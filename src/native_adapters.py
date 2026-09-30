"""Fast Windows adapter snapshot through GetAdaptersAddresses."""
import ctypes as c
from ctypes import wintypes as w
import ipaddress
import socket

class Address(c.Structure):
    _fields_=[('pointer',c.c_void_p),('length',c.c_int)]
class Unicast(c.Structure):pass
Unicast._fields_=[('alignment',c.c_ulonglong),('next',c.POINTER(Unicast)),('address',Address),
                 ('prefix',c.c_int),('suffix',c.c_int),('dad',c.c_int)]
class Adapter(c.Structure):pass
Adapter._fields_=[('alignment',c.c_ulonglong),('next',c.POINTER(Adapter)),('name',c.c_char_p),
 ('unicast',c.POINTER(Unicast)),('anycast',c.c_void_p),('multicast',c.c_void_p),('dns',c.c_void_p),
 ('suffix',c.c_wchar_p),('description',c.c_wchar_p),('friendly',c.c_wchar_p),
 ('mac',c.c_ubyte*8),('mac_length',w.ULONG),('flags',w.ULONG),('mtu',w.ULONG),
 ('kind',w.ULONG),('status',c.c_int)]

def snapshot():
    api=c.WinDLL('iphlpapi').GetAdaptersAddresses
    api.argtypes=[w.ULONG,w.ULONG,c.c_void_p,c.c_void_p,c.POINTER(w.ULONG)]
    api.restype=w.ULONG
    size=w.ULONG(16384)
    for _ in range(3):
        buf=c.create_string_buffer(size.value)
        result=api(socket.AF_INET,14,None,buf,c.byref(size))
        if result==111:continue
        if result==232:return []
        if result:raise c.WinError(result)
        rows=[]
        ptr=c.cast(buf,c.POINTER(Adapter))
        while ptr:
            a=ptr.contents
            ips=[]
            u=a.unicast
            while u:
                item=u.contents
                if item.address.pointer and item.address.length>=8 and item.dad==4:
                    raw=c.string_at(item.address.pointer,8)
                    if int.from_bytes(raw[:2],'little')==socket.AF_INET:
                        ip=ipaddress.ip_address(raw[4:8])
                        if not (ip.is_loopback or ip.is_link_local or ip.is_unspecified):ips.append(str(ip))
                u=item.next
            rows.append(dict(guid=a.name.decode('ascii').strip('{}').lower(),kind=a.kind,up=a.status==1,ips=ips))
            ptr=a.next
        return rows
    raise OSError('Adapter list changed repeatedly')
