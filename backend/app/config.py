from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    api_prefix: str
    storage_root: Path
    input_dir: Path
    output_dir: Path
    storage_backend: str
    storage_signed_url_ttl_seconds: int
    storage_s3_bucket: str
    storage_s3_region: str
    storage_s3_endpoint_url: str
    storage_s3_access_key_id: str
    storage_s3_secret_access_key: str
    storage_s3_use_ssl: bool
    database_url: str
    db_auto_init: bool
    worker_concurrency: int
    max_upload_bytes: int
    request_timeout_seconds: float
    allowed_extensions: tuple[str, ...]
    queue_backend: str
    celery_broker_url: str
    celery_result_backend: str
    job_max_attempts: int
    job_retry_base_delay_seconds: int
    retry_scheduler_interval_seconds: int
    retry_scheduler_batch_size: int
    require_api_key: bool
    default_workspace_name: str
    default_workspace_api_key: str
    default_workspace_plan: str
    default_workspace_monthly_limit: int
    default_admin_email: str
    default_admin_password: str
    default_client_email: str
    default_client_password: str
    admin_api_key: str
    billing_webhook_secret: str
    stripe_webhook_tolerance_seconds: int
    quota_scheduler_interval_seconds: int
    usage_retention_months: int
    frontend_cors_origins: tuple[str, ...]
    auth_token_secret: str
    auth_token_ttl_seconds: int
    password_reset_token_ttl_seconds: int
    password_reset_return_token_in_response: bool
    password_reset_ui_base_url: str
    email_delivery_mode: str
    email_outbox_dir: Path
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    smtp_from_email: str
    auth_rate_limit_window_seconds: int
    auth_login_rate_limit_per_ip: int
    auth_password_reset_request_rate_limit_per_ip: int
    auth_password_reset_request_rate_limit_per_email: int
    auth_password_reset_confirm_rate_limit_per_ip: int
    auth_login_lockout_threshold: int
    auth_login_lockout_seconds: int
    auth_login_failure_window_seconds: int
    auth_security_backend: str
    auth_security_redis_url: str
    auth_security_redis_key_namespace: str


def _get_csv(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def load_settings() -> Settings:
    storage_root = Path(os.getenv("PDF_SAAS_STORAGE_ROOT", "backend/storage")).resolve()
    input_dir = storage_root / "input"
    output_dir = storage_root / "output"
    storage_backend = os.getenv("PDF_SAAS_STORAGE_BACKEND", "local").strip().lower()
    max_upload_mb = _get_int("PDF_SAAS_MAX_UPLOAD_MB", 25)
    max_upload_bytes = max_upload_mb * 1024 * 1024

    raw_exts = os.getenv("PDF_SAAS_ALLOWED_EXTENSIONS", ".pdf")
    allowed_extensions = tuple(
        ext.strip().lower() if ext.startswith(".") else f".{ext.strip().lower()}"
        for ext in raw_exts.split(",")
        if ext.strip()
    )

    database_url = os.getenv("PDF_SAAS_DATABASE_URL", f"sqlite:///{(storage_root / 'app.db').as_posix()}")
    queue_backend = os.getenv("PDF_SAAS_QUEUE_BACKEND", "local").strip().lower()

    return Settings(
        app_name=os.getenv("PDF_SAAS_APP_NAME", "PDF Form SaaS"),
        api_prefix=os.getenv("PDF_SAAS_API_PREFIX", "/api/v1"),
        storage_root=storage_root,
        input_dir=input_dir,
        output_dir=output_dir,
        storage_backend=storage_backend if storage_backend in {"local", "s3"} else "local",
        storage_signed_url_ttl_seconds=max(60, _get_int("PDF_SAAS_STORAGE_SIGNED_URL_TTL_SECONDS", 900)),
        storage_s3_bucket=os.getenv("PDF_SAAS_STORAGE_S3_BUCKET", "").strip(),
        storage_s3_region=os.getenv("PDF_SAAS_STORAGE_S3_REGION", "").strip(),
        storage_s3_endpoint_url=os.getenv("PDF_SAAS_STORAGE_S3_ENDPOINT_URL", "").strip(),
        storage_s3_access_key_id=os.getenv("PDF_SAAS_STORAGE_S3_ACCESS_KEY_ID", "").strip(),
        storage_s3_secret_access_key=os.getenv("PDF_SAAS_STORAGE_S3_SECRET_ACCESS_KEY", "").strip(),
        storage_s3_use_ssl=_get_bool("PDF_SAAS_STORAGE_S3_USE_SSL", True),
        database_url=database_url,
        db_auto_init=_get_bool("PDF_SAAS_DB_AUTO_INIT", True),
        worker_concurrency=max(1, _get_int("PDF_SAAS_WORKER_CONCURRENCY", 4)),
        max_upload_bytes=max_upload_bytes,
        request_timeout_seconds=max(1.0, _get_float("PDF_SAAS_TIMEOUT_SECONDS", 60.0)),
        allowed_extensions=allowed_extensions or (".pdf",),
        queue_backend=queue_backend if queue_backend in {"local", "celery"} else "local",
        celery_broker_url=os.getenv("PDF_SAAS_CELERY_BROKER_URL", "redis://localhost:6379/0"),
        celery_result_backend=os.getenv("PDF_SAAS_CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
        job_max_attempts=max(1, _get_int("PDF_SAAS_JOB_MAX_ATTEMPTS", 3)),
        job_retry_base_delay_seconds=max(1, _get_int("PDF_SAAS_JOB_RETRY_BASE_DELAY_SECONDS", 5)),
        retry_scheduler_interval_seconds=max(1, _get_int("PDF_SAAS_RETRY_SCHEDULER_INTERVAL_SECONDS", 5)),
        retry_scheduler_batch_size=max(1, _get_int("PDF_SAAS_RETRY_SCHEDULER_BATCH_SIZE", 20)),
        require_api_key=_get_bool("PDF_SAAS_REQUIRE_API_KEY", False),
        default_workspace_name=os.getenv("PDF_SAAS_DEFAULT_WORKSPACE_NAME", "Default Workspace"),
        default_workspace_api_key=os.getenv("PDF_SAAS_DEFAULT_WORKSPACE_API_KEY", "dev-local-api-key"),
        default_workspace_plan=os.getenv("PDF_SAAS_DEFAULT_WORKSPACE_PLAN", "starter"),
        default_workspace_monthly_limit=max(1, _get_int("PDF_SAAS_DEFAULT_WORKSPACE_MONTHLY_LIMIT", 200)),
        default_admin_email=os.getenv("PDF_SAAS_DEFAULT_ADMIN_EMAIL", "admin@local.dev"),
        default_admin_password=os.getenv("PDF_SAAS_DEFAULT_ADMIN_PASSWORD", "Admin123!!"),
        default_client_email=os.getenv("PDF_SAAS_DEFAULT_CLIENT_EMAIL", "client@local.dev"),
        default_client_password=os.getenv("PDF_SAAS_DEFAULT_CLIENT_PASSWORD", "Client123!!"),
        admin_api_key=os.getenv("PDF_SAAS_ADMIN_API_KEY", "dev-admin-key"),
        billing_webhook_secret=os.getenv("PDF_SAAS_BILLING_WEBHOOK_SECRET", "dev-billing-secret"),
        stripe_webhook_tolerance_seconds=max(30, _get_int("PDF_SAAS_STRIPE_WEBHOOK_TOLERANCE_SECONDS", 300)),
        quota_scheduler_interval_seconds=max(60, _get_int("PDF_SAAS_QUOTA_SCHEDULER_INTERVAL_SECONDS", 3600)),
        usage_retention_months=max(1, _get_int("PDF_SAAS_USAGE_RETENTION_MONTHS", 15)),
        frontend_cors_origins=_get_csv(
            "PDF_SAAS_CORS_ORIGINS",
            "http://localhost:4200,http://127.0.0.1:4200",
        ),
        auth_token_secret=os.getenv("PDF_SAAS_AUTH_TOKEN_SECRET", os.getenv("PDF_SAAS_ADMIN_API_KEY", "dev-admin-key")),
        auth_token_ttl_seconds=max(300, _get_int("PDF_SAAS_AUTH_TOKEN_TTL_SECONDS", 43200)),
        password_reset_token_ttl_seconds=max(300, _get_int("PDF_SAAS_PASSWORD_RESET_TOKEN_TTL_SECONDS", 1800)),
        password_reset_return_token_in_response=_get_bool("PDF_SAAS_PASSWORD_RESET_RETURN_TOKEN", False),
        password_reset_ui_base_url=os.getenv("PDF_SAAS_PASSWORD_RESET_UI_BASE_URL", "http://localhost:4200").rstrip("/"),
        email_delivery_mode=os.getenv("PDF_SAAS_EMAIL_DELIVERY_MODE", "file").strip().lower(),
        email_outbox_dir=Path(os.getenv("PDF_SAAS_EMAIL_OUTBOX_DIR", str(storage_root / "mail_outbox"))).resolve(),
        smtp_host=os.getenv("PDF_SAAS_SMTP_HOST", "").strip(),
        smtp_port=max(1, _get_int("PDF_SAAS_SMTP_PORT", 587)),
        smtp_username=os.getenv("PDF_SAAS_SMTP_USERNAME", "").strip(),
        smtp_password=os.getenv("PDF_SAAS_SMTP_PASSWORD", ""),
        smtp_use_tls=_get_bool("PDF_SAAS_SMTP_USE_TLS", True),
        smtp_from_email=os.getenv("PDF_SAAS_SMTP_FROM_EMAIL", "no-reply@local.dev").strip(),
        auth_rate_limit_window_seconds=max(5, _get_int("PDF_SAAS_AUTH_RATE_LIMIT_WINDOW_SECONDS", 300)),
        auth_login_rate_limit_per_ip=max(1, _get_int("PDF_SAAS_AUTH_LOGIN_RATE_LIMIT_PER_IP", 30)),
        auth_password_reset_request_rate_limit_per_ip=max(
            1,
            _get_int("PDF_SAAS_AUTH_PASSWORD_RESET_REQUEST_RATE_LIMIT_PER_IP", 10),
        ),
        auth_password_reset_request_rate_limit_per_email=max(
            1,
            _get_int("PDF_SAAS_AUTH_PASSWORD_RESET_REQUEST_RATE_LIMIT_PER_EMAIL", 3),
        ),
        auth_password_reset_confirm_rate_limit_per_ip=max(
            1,
            _get_int("PDF_SAAS_AUTH_PASSWORD_RESET_CONFIRM_RATE_LIMIT_PER_IP", 12),
        ),
        auth_login_lockout_threshold=max(1, _get_int("PDF_SAAS_AUTH_LOGIN_LOCKOUT_THRESHOLD", 5)),
        auth_login_lockout_seconds=max(5, _get_int("PDF_SAAS_AUTH_LOGIN_LOCKOUT_SECONDS", 900)),
        auth_login_failure_window_seconds=max(5, _get_int("PDF_SAAS_AUTH_LOGIN_FAILURE_WINDOW_SECONDS", 900)),
        auth_security_backend=os.getenv("PDF_SAAS_AUTH_SECURITY_BACKEND", "auto").strip().lower(),
        auth_security_redis_url=os.getenv("PDF_SAAS_AUTH_SECURITY_REDIS_URL", "").strip(),
        auth_security_redis_key_namespace=os.getenv("PDF_SAAS_AUTH_SECURITY_REDIS_KEY_NAMESPACE", "pdfsaas:v1:auth").strip(),
    )


settings = load_settings()
