from ipaddress import ip_address
from urllib.parse import urlparse
import socket
ALLOWED_SCHEMES={"http","https"}
def _private_ip(host:str)->bool:
    try:
        addr=ip_address(host); return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
    except ValueError:
        try:
            return any(_private_ip(item[4][0]) for item in socket.getaddrinfo(host,None,type=socket.SOCK_STREAM))
        except OSError: return True

def validate_media_url(value:str)->str:
    value=value.strip(); p=urlparse(value)
    if p.scheme.lower() not in ALLOWED_SCHEMES or not p.netloc or p.username or p.password: raise ValueError("Only public HTTP(S) media URLs are allowed.")
    host=(p.hostname or "").lower().rstrip(".")
    if not host or host in {"localhost","localhost.localdomain"} or host.endswith(".local") or _private_ip(host): raise ValueError("Private or internal network addresses are not allowed.")
    return value
