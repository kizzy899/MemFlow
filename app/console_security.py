from __future__ import annotations

from ipaddress import ip_address
from fastapi import HTTPException, Request


def require_loopback(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host == "testclient":
        return
    try:
        if ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise HTTPException(status_code=403, detail="Knowledge Console 仅允许本机访问")