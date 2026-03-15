from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from threading import Lock
from typing import Protocol
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

from ..config import Settings

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AuthDecision:
    allowed: bool
    retry_after_seconds: int = 0
    rule: str | None = None


class AuthSecurityBackend(Protocol):
    def allow_login_attempt(self, *, ip: str, email: str) -> AuthDecision: ...

    def register_login_failure(self, *, ip: str, email: str) -> AuthDecision: ...

    def clear_login_state(self, *, ip: str, email: str) -> None: ...

    def allow_password_reset_request(self, *, ip: str, email: str) -> AuthDecision: ...

    def allow_password_reset_confirm(self, *, ip: str) -> AuthDecision: ...

    def status(self) -> dict[str, str | int | bool | None]: ...


class MemoryAuthSecurity:
    backend_name = "memory"

    def __init__(
        self,
        *,
        auth_rate_limit_window_seconds: int,
        auth_login_rate_limit_per_ip: int,
        auth_password_reset_request_rate_limit_per_ip: int,
        auth_password_reset_request_rate_limit_per_email: int,
        auth_password_reset_confirm_rate_limit_per_ip: int,
        auth_login_lockout_threshold: int,
        auth_login_lockout_seconds: int,
        auth_login_failure_window_seconds: int,
    ) -> None:
        self.auth_rate_limit_window_seconds = max(1, auth_rate_limit_window_seconds)
        self.auth_login_rate_limit_per_ip = max(1, auth_login_rate_limit_per_ip)
        self.auth_password_reset_request_rate_limit_per_ip = max(1, auth_password_reset_request_rate_limit_per_ip)
        self.auth_password_reset_request_rate_limit_per_email = max(1, auth_password_reset_request_rate_limit_per_email)
        self.auth_password_reset_confirm_rate_limit_per_ip = max(1, auth_password_reset_confirm_rate_limit_per_ip)
        self.auth_login_lockout_threshold = max(1, auth_login_lockout_threshold)
        self.auth_login_lockout_seconds = max(1, auth_login_lockout_seconds)
        self.auth_login_failure_window_seconds = max(1, auth_login_failure_window_seconds)

        self._lock = Lock()
        self._request_events: dict[str, deque[datetime]] = {}
        self._login_failures: dict[str, deque[datetime]] = {}
        self._login_lockouts: dict[str, datetime] = {}

    def allow_login_attempt(self, *, ip: str, email: str) -> AuthDecision:
        ip_key = f"login_ip:{ip}"
        with self._lock:
            now = _utc_now()
            if not self._consume_rate_limit(
                key=ip_key,
                limit=self.auth_login_rate_limit_per_ip,
                window_seconds=self.auth_rate_limit_window_seconds,
                now=now,
            ):
                retry_after = self._retry_after_seconds(
                    key=ip_key,
                    window_seconds=self.auth_rate_limit_window_seconds,
                    now=now,
                )
                return AuthDecision(False, retry_after_seconds=retry_after, rule="login_ip_rate")

            login_key = self._login_identity_key(ip=ip, email=email)
            locked_retry = self._lockout_retry_after(login_key, now)
            if locked_retry > 0:
                return AuthDecision(False, retry_after_seconds=locked_retry, rule="login_lockout")
            return AuthDecision(True)

    def register_login_failure(self, *, ip: str, email: str) -> AuthDecision:
        with self._lock:
            now = _utc_now()
            key = self._login_identity_key(ip=ip, email=email)
            failures = self._login_failures.setdefault(key, deque())
            cutoff = now - timedelta(seconds=self.auth_login_failure_window_seconds)
            while failures and failures[0] <= cutoff:
                failures.popleft()

            failures.append(now)
            if len(failures) < self.auth_login_lockout_threshold:
                return AuthDecision(True)

            self._login_lockouts[key] = now + timedelta(seconds=self.auth_login_lockout_seconds)
            self._login_failures.pop(key, None)
            return AuthDecision(False, retry_after_seconds=self.auth_login_lockout_seconds, rule="login_lockout")

    def clear_login_state(self, *, ip: str, email: str) -> None:
        with self._lock:
            key = self._login_identity_key(ip=ip, email=email)
            self._login_failures.pop(key, None)
            self._login_lockouts.pop(key, None)

    def allow_password_reset_request(self, *, ip: str, email: str) -> AuthDecision:
        ip_key = f"pwd_reset_request_ip:{ip}"
        email_key = f"pwd_reset_request_email:{email}"
        with self._lock:
            now = _utc_now()
            if not self._consume_rate_limit(
                key=ip_key,
                limit=self.auth_password_reset_request_rate_limit_per_ip,
                window_seconds=self.auth_rate_limit_window_seconds,
                now=now,
            ):
                retry_after = self._retry_after_seconds(
                    key=ip_key,
                    window_seconds=self.auth_rate_limit_window_seconds,
                    now=now,
                )
                return AuthDecision(False, retry_after_seconds=retry_after, rule="password_reset_request_ip_rate")

            if not self._consume_rate_limit(
                key=email_key,
                limit=self.auth_password_reset_request_rate_limit_per_email,
                window_seconds=self.auth_rate_limit_window_seconds,
                now=now,
            ):
                retry_after = self._retry_after_seconds(
                    key=email_key,
                    window_seconds=self.auth_rate_limit_window_seconds,
                    now=now,
                )
                return AuthDecision(False, retry_after_seconds=retry_after, rule="password_reset_request_email_rate")

            return AuthDecision(True)

    def allow_password_reset_confirm(self, *, ip: str) -> AuthDecision:
        ip_key = f"pwd_reset_confirm_ip:{ip}"
        with self._lock:
            now = _utc_now()
            if not self._consume_rate_limit(
                key=ip_key,
                limit=self.auth_password_reset_confirm_rate_limit_per_ip,
                window_seconds=self.auth_rate_limit_window_seconds,
                now=now,
            ):
                retry_after = self._retry_after_seconds(
                    key=ip_key,
                    window_seconds=self.auth_rate_limit_window_seconds,
                    now=now,
                )
                return AuthDecision(False, retry_after_seconds=retry_after, rule="password_reset_confirm_ip_rate")
            return AuthDecision(True)

    def _consume_rate_limit(self, *, key: str, limit: int, window_seconds: int, now: datetime) -> bool:
        bucket = self._request_events.setdefault(key, deque())
        cutoff = now - timedelta(seconds=window_seconds)
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= limit:
            return False

        bucket.append(now)
        return True

    def _retry_after_seconds(self, *, key: str, window_seconds: int, now: datetime) -> int:
        bucket = self._request_events.get(key)
        if not bucket:
            return 1
        retry_at = bucket[0] + timedelta(seconds=window_seconds)
        remaining = int((retry_at - now).total_seconds())
        return max(1, remaining)

    def _lockout_retry_after(self, login_key: str, now: datetime) -> int:
        locked_until = self._login_lockouts.get(login_key)
        if not locked_until:
            return 0
        if locked_until <= now:
            self._login_lockouts.pop(login_key, None)
            return 0
        remaining = int((locked_until - now).total_seconds())
        return max(1, remaining)

    @staticmethod
    def _login_identity_key(*, ip: str, email: str) -> str:
        return f"login_pair:{ip}:{email}"

    def status(self) -> dict[str, str | int | bool | None]:
        return {
            "configured_backend": "memory",
            "active_backend": "memory",
        }


class RedisAuthSecurity:
    backend_name = "redis"

    _RATE_LIMIT_LUA = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, 0, now_ms - window_ms)
local count = redis.call('ZCARD', key)

if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry = 1
  if oldest[2] then
    local unlock_ms = tonumber(oldest[2]) + window_ms
    retry = math.ceil((unlock_ms - now_ms) / 1000)
    if retry < 1 then
      retry = 1
    end
  end
  return {0, retry}
end

redis.call('ZADD', key, now_ms, member)
redis.call('PEXPIRE', key, window_ms + 60000)
return {1, 0}
"""

    _REGISTER_LOGIN_FAILURE_LUA = """
local fail_key = KEYS[1]
local lock_key = KEYS[2]
local now_ms = tonumber(ARGV[1])
local failure_window_ms = tonumber(ARGV[2])
local threshold = tonumber(ARGV[3])
local lockout_seconds = tonumber(ARGV[4])
local member = ARGV[5]

local existing_ttl = redis.call('TTL', lock_key)
if existing_ttl > 0 then
  return {0, existing_ttl}
end

redis.call('ZREMRANGEBYSCORE', fail_key, 0, now_ms - failure_window_ms)
redis.call('ZADD', fail_key, now_ms, member)
redis.call('PEXPIRE', fail_key, failure_window_ms + 60000)

local count = redis.call('ZCARD', fail_key)
if count >= threshold then
  redis.call('SET', lock_key, '1', 'EX', lockout_seconds)
  redis.call('DEL', fail_key)
  return {0, lockout_seconds}
end

return {1, 0}
"""

    def __init__(
        self,
        *,
        redis_client: Redis,
        key_namespace: str,
        auth_rate_limit_window_seconds: int,
        auth_login_rate_limit_per_ip: int,
        auth_password_reset_request_rate_limit_per_ip: int,
        auth_password_reset_request_rate_limit_per_email: int,
        auth_password_reset_confirm_rate_limit_per_ip: int,
        auth_login_lockout_threshold: int,
        auth_login_lockout_seconds: int,
        auth_login_failure_window_seconds: int,
    ) -> None:
        self.redis = redis_client
        self.key_namespace = key_namespace.strip() or "pdfsaas:v1:auth"
        self.auth_rate_limit_window_seconds = max(1, auth_rate_limit_window_seconds)
        self.auth_login_rate_limit_per_ip = max(1, auth_login_rate_limit_per_ip)
        self.auth_password_reset_request_rate_limit_per_ip = max(1, auth_password_reset_request_rate_limit_per_ip)
        self.auth_password_reset_request_rate_limit_per_email = max(1, auth_password_reset_request_rate_limit_per_email)
        self.auth_password_reset_confirm_rate_limit_per_ip = max(1, auth_password_reset_confirm_rate_limit_per_ip)
        self.auth_login_lockout_threshold = max(1, auth_login_lockout_threshold)
        self.auth_login_lockout_seconds = max(1, auth_login_lockout_seconds)
        self.auth_login_failure_window_seconds = max(1, auth_login_failure_window_seconds)

        self._rate_limit_script = self.redis.register_script(self._RATE_LIMIT_LUA)
        self._register_login_failure_script = self.redis.register_script(self._REGISTER_LOGIN_FAILURE_LUA)

    def allow_login_attempt(self, *, ip: str, email: str) -> AuthDecision:
        ip_decision = self._consume_rate_limit(
            key=self._key(f"login_ip:{ip}"),
            limit=self.auth_login_rate_limit_per_ip,
            window_seconds=self.auth_rate_limit_window_seconds,
            rule="login_ip_rate",
        )
        if not ip_decision.allowed:
            return ip_decision

        login_key = self._login_identity_key(ip=ip, email=email)
        ttl = int(self.redis.ttl(self._key(f"lockout:{login_key}")))
        if ttl > 0:
            return AuthDecision(False, retry_after_seconds=max(1, ttl), rule="login_lockout")
        return AuthDecision(True)

    def register_login_failure(self, *, ip: str, email: str) -> AuthDecision:
        now_ms = self._now_ms()
        login_key = self._login_identity_key(ip=ip, email=email)
        result = self._register_login_failure_script(
            keys=[self._key(f"failures:{login_key}"), self._key(f"lockout:{login_key}")],
            args=[
                now_ms,
                self.auth_login_failure_window_seconds * 1000,
                self.auth_login_lockout_threshold,
                self.auth_login_lockout_seconds,
                f"{now_ms}:{uuid4().hex}",
            ],
        )
        allowed = bool(int(result[0]))  # type: ignore[index]
        retry_after_seconds = max(0, int(result[1]))  # type: ignore[index]
        if allowed:
            return AuthDecision(True)
        return AuthDecision(False, retry_after_seconds=max(1, retry_after_seconds), rule="login_lockout")

    def clear_login_state(self, *, ip: str, email: str) -> None:
        login_key = self._login_identity_key(ip=ip, email=email)
        self.redis.delete(self._key(f"failures:{login_key}"), self._key(f"lockout:{login_key}"))

    def allow_password_reset_request(self, *, ip: str, email: str) -> AuthDecision:
        ip_decision = self._consume_rate_limit(
            key=self._key(f"pwd_reset_request_ip:{ip}"),
            limit=self.auth_password_reset_request_rate_limit_per_ip,
            window_seconds=self.auth_rate_limit_window_seconds,
            rule="password_reset_request_ip_rate",
        )
        if not ip_decision.allowed:
            return ip_decision

        return self._consume_rate_limit(
            key=self._key(f"pwd_reset_request_email:{email}"),
            limit=self.auth_password_reset_request_rate_limit_per_email,
            window_seconds=self.auth_rate_limit_window_seconds,
            rule="password_reset_request_email_rate",
        )

    def allow_password_reset_confirm(self, *, ip: str) -> AuthDecision:
        return self._consume_rate_limit(
            key=self._key(f"pwd_reset_confirm_ip:{ip}"),
            limit=self.auth_password_reset_confirm_rate_limit_per_ip,
            window_seconds=self.auth_rate_limit_window_seconds,
            rule="password_reset_confirm_ip_rate",
        )

    def _consume_rate_limit(self, *, key: str, limit: int, window_seconds: int, rule: str) -> AuthDecision:
        now_ms = self._now_ms()
        result = self._rate_limit_script(
            keys=[key],
            args=[
                now_ms,
                window_seconds * 1000,
                limit,
                f"{now_ms}:{uuid4().hex}",
            ],
        )
        allowed = bool(int(result[0]))  # type: ignore[index]
        retry_after_seconds = max(0, int(result[1]))  # type: ignore[index]
        if allowed:
            return AuthDecision(True)
        return AuthDecision(False, retry_after_seconds=max(1, retry_after_seconds), rule=rule)

    def _key(self, suffix: str) -> str:
        return f"{self.key_namespace}:{suffix}"

    @staticmethod
    def _now_ms() -> int:
        return int(_utc_now().timestamp() * 1000)

    @staticmethod
    def _login_identity_key(*, ip: str, email: str) -> str:
        return f"{ip}:{email}"

    def status(self) -> dict[str, str | int | bool | None]:
        return {
            "configured_backend": "redis",
            "active_backend": "redis",
            "redis_key_namespace": self.key_namespace,
        }


class FallbackAuthSecurity:
    def __init__(self, primary: AuthSecurityBackend, fallback: AuthSecurityBackend) -> None:
        self.primary = primary
        self.fallback = fallback
        self._status_lock = Lock()
        self._last_backend = self._backend_name(primary)
        self._fallback_activations = 0

    def allow_login_attempt(self, *, ip: str, email: str) -> AuthDecision:
        return self._call("allow_login_attempt", ip=ip, email=email)

    def register_login_failure(self, *, ip: str, email: str) -> AuthDecision:
        return self._call("register_login_failure", ip=ip, email=email)

    def clear_login_state(self, *, ip: str, email: str) -> None:
        self._call("clear_login_state", ip=ip, email=email)

    def allow_password_reset_request(self, *, ip: str, email: str) -> AuthDecision:
        return self._call("allow_password_reset_request", ip=ip, email=email)

    def allow_password_reset_confirm(self, *, ip: str) -> AuthDecision:
        return self._call("allow_password_reset_confirm", ip=ip)

    def _call(self, method: str, **kwargs):
        try:
            fn = getattr(self.primary, method)
            result = fn(**kwargs)
            with self._status_lock:
                self._last_backend = self._backend_name(self.primary)
            return result
        except RedisError as exc:
            logger.warning("Primary auth security backend failed; using fallback. method=%s error=%s", method, exc)
            fn = getattr(self.fallback, method)
            result = fn(**kwargs)
            with self._status_lock:
                self._last_backend = self._backend_name(self.fallback)
                self._fallback_activations += 1
            return result

    def status(self) -> dict[str, str | int | bool | None]:
        with self._status_lock:
            return {
                "configured_backend": "auto",
                "active_backend": self._last_backend,
                "primary_backend": self._backend_name(self.primary),
                "fallback_backend": self._backend_name(self.fallback),
                "fallback_activations": self._fallback_activations,
            }

    @staticmethod
    def _backend_name(backend: AuthSecurityBackend) -> str:
        return str(getattr(backend, "backend_name", backend.__class__.__name__.lower()))


def build_auth_security(settings: Settings) -> AuthSecurityBackend:
    memory = MemoryAuthSecurity(
        auth_rate_limit_window_seconds=settings.auth_rate_limit_window_seconds,
        auth_login_rate_limit_per_ip=settings.auth_login_rate_limit_per_ip,
        auth_password_reset_request_rate_limit_per_ip=settings.auth_password_reset_request_rate_limit_per_ip,
        auth_password_reset_request_rate_limit_per_email=settings.auth_password_reset_request_rate_limit_per_email,
        auth_password_reset_confirm_rate_limit_per_ip=settings.auth_password_reset_confirm_rate_limit_per_ip,
        auth_login_lockout_threshold=settings.auth_login_lockout_threshold,
        auth_login_lockout_seconds=settings.auth_login_lockout_seconds,
        auth_login_failure_window_seconds=settings.auth_login_failure_window_seconds,
    )

    backend = settings.auth_security_backend.strip().lower()
    if backend == "memory":
        return memory

    redis_url = settings.auth_security_redis_url.strip() or settings.celery_broker_url
    redis_client = Redis.from_url(redis_url)
    redis_backend = RedisAuthSecurity(
        redis_client=redis_client,
        key_namespace=settings.auth_security_redis_key_namespace,
        auth_rate_limit_window_seconds=settings.auth_rate_limit_window_seconds,
        auth_login_rate_limit_per_ip=settings.auth_login_rate_limit_per_ip,
        auth_password_reset_request_rate_limit_per_ip=settings.auth_password_reset_request_rate_limit_per_ip,
        auth_password_reset_request_rate_limit_per_email=settings.auth_password_reset_request_rate_limit_per_email,
        auth_password_reset_confirm_rate_limit_per_ip=settings.auth_password_reset_confirm_rate_limit_per_ip,
        auth_login_lockout_threshold=settings.auth_login_lockout_threshold,
        auth_login_lockout_seconds=settings.auth_login_lockout_seconds,
        auth_login_failure_window_seconds=settings.auth_login_failure_window_seconds,
    )

    try:
        redis_client.ping()
    except RedisError as exc:
        if backend == "redis":
            raise RuntimeError(f"Redis auth security backend is configured but unavailable: {exc}") from exc
        logger.warning("Redis auth security unavailable; using memory backend. error=%s", exc)
        return memory

    if backend == "redis":
        return redis_backend

    return FallbackAuthSecurity(redis_backend, memory)
