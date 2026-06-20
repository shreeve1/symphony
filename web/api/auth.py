from __future__ import annotations

import base64
import hmac
import json
import os
import time
from dataclasses import dataclass
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from typing import Any, cast

_bcrypt = cast(Any, import_module("bcrypt"))

COOKIE_NAME = "podium_session"
SESSION_MAX_AGE_SECONDS = 86_400
FAILED_LOGIN_LIMIT = 5
FAILED_LOGIN_WINDOW_SECONDS = 60
REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AuthConfig:
    password_hash: str
    session_secret: str
    api_token: str | None = None


_failed_attempts: dict[str, list[float]] = {}


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def config_from_environment() -> AuthConfig:
    load_dotenv()
    password_hash = os.environ.get("PODIUM_PASSWORD_HASH")
    session_secret = os.environ.get("PODIUM_SESSION_SECRET")
    missing = [
        name
        for name, value in (
            ("PODIUM_PASSWORD_HASH", password_hash),
            ("PODIUM_SESSION_SECRET", session_secret),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"Podium auth env missing: {', '.join(missing)}")
    assert password_hash is not None
    assert session_secret is not None
    # Optional service-to-service Bearer token (PODIUM_API_TOKEN). Unset → the
    # API stays cookie-only and `verify_bearer_token` always returns False.
    api_token = os.environ.get("PODIUM_API_TOKEN") or None
    return AuthConfig(
        password_hash=password_hash,
        session_secret=session_secret,
        api_token=api_token,
    )


def verify_password(password: str, config: AuthConfig) -> bool:
    return _bcrypt.checkpw(password.encode(), config.password_hash.encode())


def verify_bearer_token(header_value: str | None, config: AuthConfig) -> bool:
    """Validate an ``Authorization: Bearer <token>`` header against the config.

    Returns False when no service token is configured, the header is missing or
    malformed, or the token does not match. The comparison is constant-time.
    """
    if not config.api_token or not header_value:
        return False
    scheme, _, token = header_value.strip().partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        return False
    return hmac.compare_digest(token, config.api_token)


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def sign_session(config: AuthConfig, now: int | None = None) -> str:
    issued_at = now or int(time.time())
    payload = _b64(json.dumps({"iat": issued_at}, separators=(",", ":")).encode())
    signature = _signature(payload, config.session_secret)
    return f"{payload}.{signature}"


def verify_session(cookie_value: str | None, config: AuthConfig) -> bool:
    if not cookie_value or "." not in cookie_value:
        return False
    payload, signature = cookie_value.rsplit(".", 1)
    if not hmac.compare_digest(signature, _signature(payload, config.session_secret)):
        return False
    try:
        data = json.loads(_unb64(payload))
        issued_at = int(data["iat"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return 0 <= time.time() - issued_at <= SESSION_MAX_AGE_SECONDS


def rate_limited(ip: str, now: float | None = None) -> bool:
    current = now or time.time()
    attempts = _recent_attempts(ip, current)
    _failed_attempts[ip] = attempts
    return len(attempts) >= FAILED_LOGIN_LIMIT


def record_failed_attempt(ip: str, now: float | None = None) -> None:
    current = now or time.time()
    attempts = _recent_attempts(ip, current)
    attempts.append(current)
    _failed_attempts[ip] = attempts


def clear_failed_attempts(ip: str) -> None:
    _failed_attempts.pop(ip, None)


def reset_rate_limits() -> None:
    _failed_attempts.clear()


def _recent_attempts(ip: str, current: float) -> list[float]:
    cutoff = current - FAILED_LOGIN_WINDOW_SECONDS
    return [stamp for stamp in _failed_attempts.get(ip, []) if stamp >= cutoff]


def _signature(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), sha256).digest()
    return _b64(digest)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
