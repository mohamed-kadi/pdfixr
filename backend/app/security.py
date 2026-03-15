from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timezone


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def key_prefix(api_key: str, length: int = 8) -> str:
    return api_key[:length]


def generate_api_key(prefix: str = "pfs") -> str:
    token = secrets.token_urlsafe(24)
    return f"{prefix}_{token}"


def hash_password(password: str, *, iterations: int = 200_000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_raw, salt_hex, digest_hex = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def issue_auth_token(
    *,
    secret: str,
    kind: str,
    ttl_seconds: int,
    claims: dict[str, str],
) -> tuple[str, datetime]:
    now = int(time.time())
    exp = now + max(60, ttl_seconds)
    payload = {
        "kind": kind,
        "iat": now,
        "exp": exp,
        **claims,
    }
    token = _encode_signed_payload(payload, secret=secret)
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    return token, expires_at


def verify_auth_token(
    token: str,
    *,
    secret: str,
    expected_kind: str | None = None,
) -> dict[str, object]:
    payload = _decode_signed_payload(token, secret=secret)
    now = int(time.time())
    exp_raw = payload.get("exp")
    if not isinstance(exp_raw, int):
        raise ValueError("Token has invalid expiration.")
    if now >= exp_raw:
        raise ValueError("Token expired.")

    kind_raw = payload.get("kind")
    if expected_kind and kind_raw != expected_kind:
        raise ValueError("Token kind mismatch.")
    return payload


def extract_bearer_token(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    scheme, _, token = authorization_header.strip().partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _encode_signed_payload(payload: dict[str, object], *, secret: str) -> str:
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64_encode(payload_json)
    signature = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = _b64_encode(signature)
    return f"{payload_b64}.{sig_b64}"


def _decode_signed_payload(token: str, *, secret: str) -> dict[str, object]:
    payload_b64, dot, sig_b64 = token.partition(".")
    if not dot or not payload_b64 or not sig_b64:
        raise ValueError("Malformed token.")

    expected_sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    actual_sig = _b64_decode(sig_b64)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("Invalid token signature.")

    payload_bytes = _b64_decode(payload_b64)
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid token payload.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Invalid token payload shape.")
    return payload


def _b64_encode(data: bytes) -> str:
    return urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    try:
        return urlsafe_b64decode(data + padding)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid base64 value.") from exc
