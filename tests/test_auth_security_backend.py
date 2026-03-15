from __future__ import annotations

from types import SimpleNamespace

import pytest
from redis.exceptions import RedisError

from backend.app.services import auth_security


def _settings(**overrides):
    defaults = {
        "auth_rate_limit_window_seconds": 300,
        "auth_login_rate_limit_per_ip": 30,
        "auth_password_reset_request_rate_limit_per_ip": 10,
        "auth_password_reset_request_rate_limit_per_email": 3,
        "auth_password_reset_confirm_rate_limit_per_ip": 12,
        "auth_login_lockout_threshold": 5,
        "auth_login_lockout_seconds": 900,
        "auth_login_failure_window_seconds": 900,
        "auth_security_backend": "memory",
        "auth_security_redis_url": "",
        "auth_security_redis_key_namespace": "pdfsaas:test:auth",
        "celery_broker_url": "redis://localhost:6379/0",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_build_auth_security_memory_backend():
    backend = auth_security.build_auth_security(_settings(auth_security_backend="memory"))
    assert isinstance(backend, auth_security.MemoryAuthSecurity)
    assert backend.status()["configured_backend"] == "memory"
    assert backend.status()["active_backend"] == "memory"


def test_build_auth_security_auto_falls_back_when_redis_unavailable(monkeypatch):
    class DummyRedis:
        def register_script(self, _script):
            def _runner(*, keys, args):
                return [1, 0]

            return _runner

        def ping(self):
            raise RedisError("redis unavailable")

    monkeypatch.setattr(auth_security.Redis, "from_url", staticmethod(lambda _url: DummyRedis()))
    backend = auth_security.build_auth_security(_settings(auth_security_backend="auto"))
    assert isinstance(backend, auth_security.MemoryAuthSecurity)


def test_build_auth_security_redis_backend_raises_when_unavailable(monkeypatch):
    class DummyRedis:
        def register_script(self, _script):
            def _runner(*, keys, args):
                return [1, 0]

            return _runner

        def ping(self):
            raise RedisError("redis unavailable")

    monkeypatch.setattr(auth_security.Redis, "from_url", staticmethod(lambda _url: DummyRedis()))
    with pytest.raises(RuntimeError):
        auth_security.build_auth_security(_settings(auth_security_backend="redis"))
