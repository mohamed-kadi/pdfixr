from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from .models import BillingStatus, JobStatus, UserRole


class HealthResponse(BaseModel):
    status: str
    queue_backend: str


class AuthSecurityStatusResponse(BaseModel):
    configured_backend: str
    active_backend: str
    details: dict[str, str | int | bool | None] = Field(default_factory=dict)


class JobResponse(BaseModel):
    id: str
    workspace_id: str
    status: JobStatus
    original_filename: str
    created_at: datetime
    updated_at: datetime
    output_ready: bool
    error_message: str | None = None
    download_url: str | None = None


class JobListResponse(BaseModel):
    items: list[JobResponse]


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    plan_name: str = Field(default="starter", min_length=2, max_length=64)
    monthly_job_limit: int | None = Field(default=None, ge=1, le=1_000_000)


class WorkspaceCreateResponse(BaseModel):
    id: str
    name: str
    plan_name: str
    monthly_job_limit: int
    api_key: str
    api_key_prefix: str
    created_at: datetime


class WorkspaceInfoResponse(BaseModel):
    id: str
    name: str
    plan_name: str
    monthly_job_limit: int
    billing_status: BillingStatus
    api_key_prefix: str
    current_period_start: date
    current_period_jobs: int
    remaining_jobs: int
    created_at: datetime


class UserResponse(BaseModel):
    id: str
    email: str
    role: UserRole
    workspace_id: str | None
    is_active: bool
    created_at: datetime


class UserLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)


class UserLoginResponse(BaseModel):
    token: str
    token_type: str
    expires_at: datetime
    user: UserResponse


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class PasswordResetRequestResponse(BaseModel):
    status: str
    message: str
    reset_token: str | None = None
    expires_at: datetime | None = None


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=20, max_length=4096)
    new_password: str = Field(min_length=8, max_length=256)


class PasswordResetConfirmResponse(BaseModel):
    status: str
    message: str


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)
    role: UserRole = Field(default=UserRole.CLIENT)
    workspace_id: str | None = None
    is_active: bool = Field(default=True)


class UserUpdateRequest(BaseModel):
    role: UserRole
    workspace_id: str | None = None
    is_active: bool


class UserPasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=256)


class ClientLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    access_code: str = Field(min_length=8, max_length=256)


class ClientLoginResponse(BaseModel):
    token: str
    token_type: str
    expires_at: datetime
    workspace: WorkspaceInfoResponse


class AdminLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    admin_code: str = Field(min_length=6, max_length=256)


class AdminLoginResponse(BaseModel):
    token: str
    token_type: str
    expires_at: datetime
    admin_email: str


class WorkspacePlanUpdateRequest(BaseModel):
    plan_name: str = Field(min_length=2, max_length=64)
    monthly_job_limit: int | None = Field(default=None, ge=1, le=1_000_000)
    billing_status: BillingStatus = Field(default=BillingStatus.ACTIVE)
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None


class BillingWebhookRequest(BaseModel):
    provider_event_id: str = Field(min_length=3, max_length=160)
    event_type: str = Field(min_length=2, max_length=120)
    workspace_id: str | None = None
    plan_name: str | None = Field(default=None, min_length=2, max_length=64)
    monthly_job_limit: int | None = Field(default=None, ge=1, le=1_000_000)
    billing_status: BillingStatus = Field(default=BillingStatus.ACTIVE)
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None


class BillingWebhookResponse(BaseModel):
    provider_event_id: str
    status: str
    workspace_id: str | None
    plan_name: str | None
    monthly_job_limit: int | None


class BillingEventResponse(BaseModel):
    id: str
    provider: str
    provider_event_id: str
    event_type: str
    workspace_id: str | None
    status: str
    error_message: str | None
    payload: dict
    processed_at: datetime | None
    created_at: datetime


class BillingEventListResponse(BaseModel):
    items: list[BillingEventResponse]


class AuditLogResponse(BaseModel):
    id: int
    workspace_id: str | None
    actor_type: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str | None
    details: dict
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
