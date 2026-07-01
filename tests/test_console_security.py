from starlette.requests import Request
from fastapi import HTTPException
from app.console_security import require_loopback


def request(host): return Request({"type":"http","method":"GET","path":"/","headers":[],"client":(host,1234),"server":("x",80),"scheme":"http","query_string":b""})

def test_console_security_allows_loopback_and_rejects_remote():
    require_loopback(request("127.0.0.1")); require_loopback(request("::1"))
    try: require_loopback(request("192.168.1.2"))
    except HTTPException as exc: assert exc.status_code==403
    else: assert False