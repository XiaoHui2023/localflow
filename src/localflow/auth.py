from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request, WebSocket, status


class AuthManager:
    def __init__(self, root: Path) -> None:
        self.directory = root / "secrets"
        directory_created = not self.directory.exists()
        self.directory.mkdir(parents=True, exist_ok=True)
        if directory_created and os.name != "nt":
            os.chmod(self.directory, 0o700)
        self.admin_path = self.directory / "web-admin-key"
        legacy_admin_path = self.directory / "admin-bootstrap"
        self.api_path = self.directory / "api-key"
        self.nonces: dict[str, tuple[float, int]] = {}
        self.generation = 1
        self.previous_keys: dict[int, tuple[bytes, float]] = {}
        if not self.admin_path.exists() and legacy_admin_path.exists():
            os.replace(legacy_admin_path, self.admin_path)
        for path in (self.admin_path, self.api_path):
            if not path.exists():
                self._atomic_secret(path, secrets.token_urlsafe(48))
        self.check_permissions()

    def _atomic_secret(self, path: Path, value: str) -> None:
        temporary = path.with_suffix(".new")
        temporary.write_text(value, encoding="ascii")
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)

    def check_permissions(self) -> None:
        if os.name == "nt":
            return
        directory = self.directory.lstat()
        if (
            self.directory.is_symlink()
            or not self.directory.is_dir()
            or directory.st_uid != os.getuid()
            or directory.st_mode & 0o077
        ):
            raise PermissionError(
                f"secret directory must be owner-owned mode 0700: {self.directory}"
            )
        for path in (self.admin_path, self.api_path):
            metadata = path.lstat()
            if (
                path.is_symlink()
                or not path.is_file()
                or metadata.st_uid != os.getuid()
                or metadata.st_nlink != 1
                or metadata.st_mode & 0o077
            ):
                raise PermissionError(f"secret must be a regular owner-only file: {path}")

    def exchange_admin(self, key: str) -> tuple[str, str]:
        expected = self.admin_path.read_text(encoding="ascii").strip()
        if not hmac.compare_digest(key, expected):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid administrator key")
        return self.create_admin_session()

    def create_admin_session(self) -> tuple[str, str]:
        nonce = secrets.token_urlsafe(32)
        signature = self._admin_signature("session", nonce)
        token = f"v1.{nonce}.{signature}"
        return token, self._csrf_token(token)

    def _admin_signature(self, purpose: str, value: str) -> str:
        key = self.admin_path.read_text(encoding="ascii").strip().encode()
        return hmac.new(
            key,
            f"localflow-web-{purpose}\0{value}".encode(),
            hashlib.sha256,
        ).hexdigest()

    def _csrf_token(self, token: str) -> str:
        return self._admin_signature("csrf", token)

    def _session(self, token: str) -> bool:
        try:
            version, nonce, supplied = token.split(".", 2)
        except ValueError:
            return False
        if version != "v1" or not nonce or not supplied:
            return False
        return hmac.compare_digest(
            supplied,
            self._admin_signature("session", nonce),
        )

    def is_admin(self, request: Request) -> bool:
        bearer = request.headers.get("authorization", "")
        token = (
            bearer[7:]
            if bearer.startswith("Bearer ")
            else request.cookies.get("localflow_session", "")
        )
        return self._session(token)

    def csrf_for(self, request: Request) -> str | None:
        token = request.cookies.get("localflow_session", "")
        return self._csrf_token(token) if self._session(token) else None

    def cookie_token(self, request: Request) -> str | None:
        token = request.cookies.get("localflow_session", "")
        return token if self._session(token) else None

    @staticmethod
    def _http_origin(request: Request) -> str:
        return f"{request.url.scheme}://{request.headers.get('host', '')}"

    def is_admin_mutation(self, request: Request) -> bool:
        token = request.cookies.get("localflow_session", "")
        authenticated = self._session(token)
        supplied = request.headers.get("x-csrf-token", "")
        origin = request.headers.get("origin", "")
        return bool(
            authenticated
            and origin == self._http_origin(request)
            and supplied
            and hmac.compare_digest(supplied, self._csrf_token(token))
        )

    def is_websocket_admin(self, websocket: WebSocket) -> bool:
        authenticated = self._session(websocket.cookies.get("localflow_session", ""))
        scheme = "https" if websocket.url.scheme == "wss" else "http"
        expected_origin = f"{scheme}://{websocket.headers.get('host', '')}"
        return bool(authenticated and websocket.headers.get("origin", "") == expected_origin)

    def issue_nonce(self) -> dict[str, object]:
        nonce = secrets.token_urlsafe(24)
        self.nonces[nonce] = (time.time() + 30, self.generation)
        return {"nonce": nonce, "generation": self.generation, "expires_in": 30}

    async def is_signed(self, request: Request) -> bool:
        nonce = request.headers.get("x-localflow-nonce", "")
        created = request.headers.get("x-localflow-created", "")
        generation = request.headers.get("x-localflow-generation", "")
        supplied = request.headers.get("x-localflow-signature", "")
        challenge = self.nonces.pop(nonce, (0, 0))
        try:
            created_value = int(created)
        except ValueError:
            return False
        if (
            challenge[0] < time.time()
            or abs(time.time() - created_value) > 30
            or generation != str(challenge[1])
        ):
            return False
        body = await request.body()
        digest = hashlib.sha256(body).hexdigest()
        canonical = "\n".join(
            (
                request.method,
                request.url.path + (f"?{request.url.query}" if request.url.query else ""),
                digest,
                generation,
                created,
                nonce,
            )
        )
        if challenge[1] == self.generation:
            key = self.api_path.read_text(encoding="ascii").strip().encode()
        elif (
            challenge[1] in self.previous_keys
            and self.previous_keys[challenge[1]][1] > time.time()
        ):
            key = self.previous_keys[challenge[1]][0]
        else:
            return False
        expected = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(supplied, expected)

    def rotate_api_key(self) -> None:
        now = time.time()
        self.previous_keys = {
            generation: entry
            for generation, entry in self.previous_keys.items()
            if entry[1] > now
        }
        old_key = self.api_path.read_text(encoding="ascii").strip().encode()
        self.previous_keys[self.generation] = (old_key, now + 30)
        self.generation += 1
        self._atomic_secret(self.api_path, secrets.token_urlsafe(48))
