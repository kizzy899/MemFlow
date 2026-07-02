from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class AuthKeyError(RuntimeError):
    pass


class CookieStore:
    """Encrypted provider-state store. Plain cookies never touch disk."""

    def __init__(self, path: Path, key: str) -> None:
        self.path = path
        self.key = key.strip()

    def _cipher(self) -> Fernet:
        if not self.key:
            raise AuthKeyError("MEMFLOW_AUTH_KEY is not configured")
        try:
            return Fernet(self.key.encode())
        except (ValueError, TypeError) as exc:
            raise AuthKeyError("MEMFLOW_AUTH_KEY must be a Fernet key") from exc

    @property
    def configured(self) -> bool:
        try:
            self._cipher()
            return True
        except AuthKeyError:
            return False

    def save(self, payload: dict[str, Any]) -> None:
        token = self._cipher().encrypt(json.dumps(payload, ensure_ascii=False).encode())
        envelope = {"version": 1, "algorithm": "Fernet-AES128-CBC-HMAC", "ciphertext": token.decode()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        envelope = json.loads(self.path.read_text(encoding="utf-8"))
        try:
            raw = self._cipher().decrypt(envelope["ciphertext"].encode())
        except InvalidToken as exc:
            raise AuthKeyError("saved session cannot be decrypted") from exc
        return json.loads(raw)

    def delete(self) -> None:
        if self.path.exists():
            self.path.unlink()
