from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuthState(StrEnum):
    IDLE = "idle"
    CHECKING = "checking"
    WAITING_SCAN = "waiting_scan"
    SCANNED = "scanned"
    CONFIRMING = "confirming"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    FAILED = "failed"
    REAUTH_REQUIRED = "reauth_required"


@dataclass
class SessionManager:
    state: AuthState = AuthState.IDLE
    qr_id: str = ""
    qr_image: str = ""
    qr_expires_at: datetime | None = None
    storage_state: dict[str, Any] | None = None
    account: dict[str, str] = field(default_factory=lambda: {"id": "", "nickname": "", "avatarUrl": ""})
    login_time: datetime | None = None
    updated_at: datetime = field(default_factory=utcnow)
    expire_at: datetime | None = None
    error: dict[str, Any] | None = None
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def status(self) -> dict[str, Any]:
        with self.lock:
            remaining = max(0, int((self.qr_expires_at - utcnow()).total_seconds())) if self.qr_expires_at else None
            return {"qrId": self.qr_id, "status": self.state.value, "expireTime": self.qr_expires_at.isoformat() if self.qr_expires_at else None, "remainingSeconds": remaining, "error": self.error}

    def public(self) -> dict[str, Any]:
        with self.lock:
            remaining = max(0, int((self.expire_at - utcnow()).total_seconds())) if self.expire_at else None
            return {"status": self.state.value, "loggedIn": self.state == AuthState.AUTHENTICATED, "cookieValid": self.state == AuthState.AUTHENTICATED, "account": self.account, "loginTime": self.login_time.isoformat() if self.login_time else None, "updatedAt": self.updated_at.isoformat(), "expireAt": self.expire_at.isoformat() if self.expire_at else None, "remainingSeconds": remaining, "error": self.error}
