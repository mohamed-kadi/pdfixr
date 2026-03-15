from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse, Response

from ..config import settings
from ..dependencies import get_current_user, get_current_workspace, require_admin
from ..models import BillingEventStatus, BillingStatus, Job, JobStatus, User, UserRole, Workspace
from ..repository import AuditRepository, BillingRepository, JobRepository, UsageRepository, UserRepository, WorkspaceRepository
from ..schemas import (
    AdminLoginRequest,
    AdminLoginResponse,
    AuthSecurityStatusResponse,
    AuditLogListResponse,
    AuditLogResponse,
    BillingEventListResponse,
    BillingEventResponse,
    BillingWebhookResponse,
    ClientLoginRequest,
    ClientLoginResponse,
    HealthResponse,
    JobListResponse,
    JobResponse,
    PasswordResetConfirmRequest,
    PasswordResetConfirmResponse,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    UserCreateRequest,
    UserLoginRequest,
    UserLoginResponse,
    UserPasswordResetRequest,
    UserResponse,
    UserUpdateRequest,
    WorkspaceCreateRequest,
    WorkspaceCreateResponse,
    WorkspaceInfoResponse,
    WorkspacePlanUpdateRequest,
)
from ..security import (
    generate_api_key,
    hash_api_key,
    hash_password,
    issue_auth_token,
    key_prefix,
    verify_auth_token,
    verify_password,
)
from ..services.plans import (
    is_processing_allowed_for_billing_status,
    period_start_utc,
    resolve_limit_for_update,
    resolve_monthly_limit,
)
from ..services.mailer import PasswordResetEmail
from ..services.storage import StorageError
from ..services.stripe_webhook import StripeSignatureError, normalize_billing_payload, verify_stripe_signature

router = APIRouter()


def _to_job_response(request: Request, job: Job) -> JobResponse:
    download_url = None
    if job.status == JobStatus.COMPLETED and job.output_path:
        download_url = str(request.url_for("download_job_result", job_id=job.id))

    return JobResponse(
        id=job.id,
        workspace_id=job.workspace_id,
        status=job.status,
        original_filename=job.original_filename,
        created_at=job.created_at,
        updated_at=job.updated_at,
        output_ready=job.status == JobStatus.COMPLETED and bool(job.output_path),
        error_message=job.error_message,
        download_url=download_url,
    )


def _workspace_info(repo: UsageRepository, workspace: Workspace) -> WorkspaceInfoResponse:
    period = period_start_utc()
    usage = repo.get_or_create(workspace_id=workspace.id, period_start=period)
    remaining = max(0, workspace.monthly_job_limit - usage.jobs_count)

    return WorkspaceInfoResponse(
        id=workspace.id,
        name=workspace.name,
        plan_name=workspace.plan_name,
        monthly_job_limit=workspace.monthly_job_limit,
        billing_status=workspace.billing_status,
        api_key_prefix=workspace.api_key_prefix,
        current_period_start=period,
        current_period_jobs=usage.jobs_count,
        remaining_jobs=remaining,
        created_at=workspace.created_at,
    )


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        workspace_id=user.workspace_id,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _password_reset_version(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def _request_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _raise_rate_limit(detail: str, retry_after_seconds: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(max(1, retry_after_seconds))},
    )


def _resolve_workspace_for_billing_payload(ws_repo: WorkspaceRepository, payload) -> Workspace | None:
    if payload.workspace_id:
        return ws_repo.get_by_id(payload.workspace_id)
    if payload.stripe_subscription_id:
        found = ws_repo.get_by_stripe_subscription_id(payload.stripe_subscription_id)
        if found:
            return found
    if payload.stripe_customer_id:
        found = ws_repo.get_by_stripe_customer_id(payload.stripe_customer_id)
        if found:
            return found
    return None


def _audit_to_response(row) -> AuditLogResponse:
    try:
        details = json.loads(row.details_json)
    except json.JSONDecodeError:
        details = {"raw": row.details_json}

    return AuditLogResponse(
        id=row.id,
        workspace_id=row.workspace_id,
        actor_type=row.actor_type,
        actor_id=row.actor_id,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        details=details,
        created_at=row.created_at,
    )


def _billing_event_to_response(row) -> BillingEventResponse:
    try:
        payload = json.loads(row.raw_payload)
    except json.JSONDecodeError:
        payload = {"raw": row.raw_payload}

    return BillingEventResponse(
        id=row.id,
        provider=row.provider,
        provider_event_id=row.provider_event_id,
        event_type=row.event_type,
        workspace_id=row.workspace_id,
        status=row.status.value,
        error_message=row.error_message,
        payload=payload,
        processed_at=row.processed_at,
        created_at=row.created_at,
    )


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    return HealthResponse(status="ok", queue_backend=request.app.state.settings.queue_backend)


@router.get("/auth/security/backend", response_model=AuthSecurityStatusResponse)
def auth_security_backend_status(request: Request, _: None = Depends(require_admin)) -> AuthSecurityStatusResponse:
    raw_status = request.app.state.auth_security.status()
    configured_backend = str(raw_status.get("configured_backend", "unknown"))
    active_backend = str(raw_status.get("active_backend", "unknown"))
    details = {key: value for key, value in raw_status.items() if key not in {"configured_backend", "active_backend"}}
    return AuthSecurityStatusResponse(
        configured_backend=configured_backend,
        active_backend=active_backend,
        details=details,
    )


@router.post("/auth/client/login", response_model=ClientLoginResponse)
def client_login(payload: ClientLoginRequest, request: Request) -> ClientLoginResponse:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        ws_repo = WorkspaceRepository(session)
        usage_repo = UsageRepository(session)
        workspace = ws_repo.get_by_api_key_hash(hash_api_key(payload.access_code.strip()))
        if not workspace:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code.")

        token, expires_at = issue_auth_token(
            secret=settings.auth_token_secret,
            kind="workspace",
            ttl_seconds=settings.auth_token_ttl_seconds,
            claims={
                "workspace_id": workspace.id,
                "api_key_prefix": workspace.api_key_prefix,
                "email": payload.email.strip().lower(),
            },
        )
        return ClientLoginResponse(
            token=token,
            token_type="bearer",
            expires_at=expires_at,
            workspace=_workspace_info(usage_repo, workspace),
        )


@router.post("/auth/admin/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest) -> AdminLoginResponse:
    if payload.admin_code.strip() != settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin code.")

    token, expires_at = issue_auth_token(
        secret=settings.auth_token_secret,
        kind="admin",
        ttl_seconds=settings.auth_token_ttl_seconds,
        claims={
            "email": payload.email.strip().lower(),
        },
    )
    return AdminLoginResponse(
        token=token,
        token_type="bearer",
        expires_at=expires_at,
        admin_email=payload.email.strip().lower(),
    )


@router.post("/auth/login", response_model=UserLoginResponse)
def user_login(payload: UserLoginRequest, request: Request) -> UserLoginResponse:
    session_factory = request.app.state.session_factory
    auth_security = request.app.state.auth_security
    email = payload.email.strip().lower()
    ip = _request_ip(request)

    with session_factory() as session:
        users = UserRepository(session)
        ws_repo = WorkspaceRepository(session)
        audit_repo = AuditRepository(session)

        login_allowed = auth_security.allow_login_attempt(ip=ip, email=email)
        if not login_allowed.allowed:
            audit_repo.create(
                actor_type="system",
                actor_id=ip,
                action="auth.login_blocked",
                resource_type="auth",
                details={
                    "email": email,
                    "ip": ip,
                    "rule": login_allowed.rule,
                    "retry_after_seconds": login_allowed.retry_after_seconds,
                },
            )
            _raise_rate_limit("Too many authentication attempts. Try again later.", login_allowed.retry_after_seconds)

        user = users.get_by_email(email)
        if not user or not verify_password(payload.password, user.password_hash):
            lockout_state = auth_security.register_login_failure(ip=ip, email=email)
            audit_repo.create(
                actor_type="system",
                actor_id=ip,
                action="auth.login_failed",
                resource_type="auth",
                details={
                    "email": email,
                    "ip": ip,
                    "rule": lockout_state.rule,
                    "retry_after_seconds": lockout_state.retry_after_seconds,
                },
            )
            if not lockout_state.allowed:
                _raise_rate_limit("Too many failed login attempts. Try again later.", lockout_state.retry_after_seconds)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive.")

        auth_security.clear_login_state(ip=ip, email=email)

        claims: dict[str, str] = {
            "user_id": user.id,
            "role": user.role.value,
            "email": user.email,
        }
        if user.role == UserRole.CLIENT:
            if not user.workspace_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Client user is not linked to any workspace.",
                )
            workspace = ws_repo.get_by_id(user.workspace_id)
            if not workspace or not workspace.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Workspace linked to this client user is inactive.",
                )
            claims["workspace_id"] = user.workspace_id

        token, expires_at = issue_auth_token(
            secret=settings.auth_token_secret,
            kind="user",
            ttl_seconds=settings.auth_token_ttl_seconds,
            claims=claims,
        )
        return UserLoginResponse(
            token=token,
            token_type="bearer",
            expires_at=expires_at,
            user=_to_user_response(user),
        )


@router.get("/auth/me", response_model=UserResponse)
def auth_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return _to_user_response(current_user)


@router.post("/auth/password-reset/request", response_model=PasswordResetRequestResponse)
def request_password_reset(payload: PasswordResetRequest, request: Request) -> PasswordResetRequestResponse:
    session_factory = request.app.state.session_factory
    auth_security = request.app.state.auth_security
    message = "If this email exists, a password reset link has been generated."
    email = payload.email.strip().lower()
    ip = _request_ip(request)

    with session_factory() as session:
        users = UserRepository(session)
        audit_repo = AuditRepository(session)

        reset_allowed = auth_security.allow_password_reset_request(ip=ip, email=email)
        if not reset_allowed.allowed:
            audit_repo.create(
                actor_type="system",
                actor_id=ip,
                action="auth.password_reset_request_blocked",
                resource_type="auth",
                details={
                    "email": email,
                    "ip": ip,
                    "rule": reset_allowed.rule,
                    "retry_after_seconds": reset_allowed.retry_after_seconds,
                },
            )
            _raise_rate_limit("Too many password reset requests. Try again later.", reset_allowed.retry_after_seconds)

        user = users.get_by_email(email)
        if not user or not user.is_active:
            return PasswordResetRequestResponse(status="accepted", message=message)

        token, expires_at = issue_auth_token(
            secret=settings.auth_token_secret,
            kind="password_reset",
            ttl_seconds=settings.password_reset_token_ttl_seconds,
            claims={
                "user_id": user.id,
                "email": user.email,
                "pwdv": _password_reset_version(user.password_hash),
            },
        )
        reset_url = f"{settings.password_reset_ui_base_url}/reset-password?token={quote(token, safe='')}"
        mailer = request.app.state.password_reset_mailer
        try:
            mailer.send_password_reset_email(
                PasswordResetEmail(
                    to_email=user.email,
                    reset_url=reset_url,
                    expires_at=expires_at,
                )
            )
            audit_repo.create(
                actor_type="system",
                actor_id="mailer",
                action="user.password_reset_email_sent",
                resource_type="user",
                resource_id=user.id,
                workspace_id=user.workspace_id,
                details={"email": user.email},
            )
        except Exception as exc:
            audit_repo.create(
                actor_type="system",
                actor_id="mailer",
                action="user.password_reset_email_failed",
                resource_type="user",
                resource_id=user.id,
                workspace_id=user.workspace_id,
                details={"email": user.email, "error": str(exc)},
            )

        audit_repo.create(
            actor_type="user",
            actor_id=user.email,
            action="user.password_reset_requested",
            resource_type="user",
            resource_id=user.id,
            workspace_id=user.workspace_id,
            details={"email": user.email},
        )
        return PasswordResetRequestResponse(
            status="accepted",
            message=message,
            reset_token=token if settings.password_reset_return_token_in_response else None,
            expires_at=expires_at if settings.password_reset_return_token_in_response else None,
        )


@router.post("/auth/password-reset/confirm", response_model=PasswordResetConfirmResponse)
def confirm_password_reset(payload: PasswordResetConfirmRequest, request: Request) -> PasswordResetConfirmResponse:
    session_factory = request.app.state.session_factory
    auth_security = request.app.state.auth_security
    ip = _request_ip(request)

    confirm_allowed = auth_security.allow_password_reset_confirm(ip=ip)
    if not confirm_allowed.allowed:
        with session_factory() as session:
            audit_repo = AuditRepository(session)
            audit_repo.create(
                actor_type="system",
                actor_id=ip,
                action="auth.password_reset_confirm_blocked",
                resource_type="auth",
                details={
                    "ip": ip,
                    "rule": confirm_allowed.rule,
                    "retry_after_seconds": confirm_allowed.retry_after_seconds,
                },
            )
        _raise_rate_limit("Too many password reset attempts. Try again later.", confirm_allowed.retry_after_seconds)

    try:
        claims = verify_auth_token(
            payload.token.strip(),
            secret=settings.auth_token_secret,
            expected_kind="password_reset",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid or expired reset token: {exc}") from exc

    user_id = claims.get("user_id")
    token_pwdv = claims.get("pwdv")
    if not isinstance(user_id, str) or not user_id or not isinstance(token_pwdv, str) or not token_pwdv:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Reset token payload is invalid.")

    with session_factory() as session:
        users = UserRepository(session)
        audit_repo = AuditRepository(session)

        user = users.get_by_id(user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Reset token is no longer valid.")

        if _password_reset_version(user.password_hash) != token_pwdv:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Reset token was already used or invalidated.")

        users.reset_password(user, password_hash=hash_password(payload.new_password))
        audit_repo.create(
            actor_type="user",
            actor_id=user.email,
            action="user.password_reset_completed",
            resource_type="user",
            resource_id=user.id,
            workspace_id=user.workspace_id,
            details={"email": user.email},
        )

    return PasswordResetConfirmResponse(status="ok", message="Password has been reset. You can sign in now.")


@router.get("/users", response_model=list[UserResponse])
def list_users(request: Request, _: None = Depends(require_admin)) -> list[UserResponse]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        users = UserRepository(session)
        rows = users.list_all(limit=500)
        return [_to_user_response(user) for user in rows]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    request: Request,
    _: None = Depends(require_admin),
) -> UserResponse:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        users = UserRepository(session)
        ws_repo = WorkspaceRepository(session)
        audit_repo = AuditRepository(session)

        email = payload.email.strip().lower()
        if users.get_by_email(email):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User email already exists.")

        workspace_id = payload.workspace_id
        if payload.role == UserRole.CLIENT:
            if not workspace_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Client user requires workspace_id.")
            workspace = ws_repo.get_by_id(workspace_id)
            if not workspace:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
        else:
            workspace_id = None

        user = users.create(
            User(
                id=str(uuid4()),
                email=email,
                password_hash=hash_password(payload.password),
                role=payload.role,
                workspace_id=workspace_id,
                is_active=payload.is_active,
            )
        )
        audit_repo.create(
            actor_type="admin",
            actor_id="admin",
            action="user.created",
            resource_type="user",
            resource_id=user.id,
            workspace_id=user.workspace_id,
            details={
                "email": user.email,
                "role": user.role.value,
                "is_active": user.is_active,
                "workspace_id": user.workspace_id,
            },
        )
        return _to_user_response(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    request: Request,
    _: None = Depends(require_admin),
) -> UserResponse:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        users = UserRepository(session)
        ws_repo = WorkspaceRepository(session)
        audit_repo = AuditRepository(session)

        user = users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        workspace_id = payload.workspace_id.strip() if payload.workspace_id else None
        if payload.role == UserRole.CLIENT:
            if not workspace_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Client user requires workspace_id.")
            workspace = ws_repo.get_by_id(workspace_id)
            if not workspace:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
        else:
            workspace_id = None

        if user.role == UserRole.ADMIN and user.is_active and not payload.is_active and users.count_active_admins() <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active admin user.",
            )

        previous = {
            "role": user.role.value,
            "workspace_id": user.workspace_id,
            "is_active": user.is_active,
        }
        user = users.update(
            user,
            role=payload.role,
            workspace_id=workspace_id,
            is_active=payload.is_active,
        )
        audit_repo.create(
            actor_type="admin",
            actor_id="admin",
            action="user.updated",
            resource_type="user",
            resource_id=user.id,
            workspace_id=user.workspace_id,
            details={
                "email": user.email,
                "previous": previous,
                "new": {
                    "role": user.role.value,
                    "workspace_id": user.workspace_id,
                    "is_active": user.is_active,
                },
            },
        )
        return _to_user_response(user)


@router.post("/users/{user_id}/reset-password", response_model=UserResponse)
def reset_user_password(
    user_id: str,
    payload: UserPasswordResetRequest,
    request: Request,
    _: None = Depends(require_admin),
) -> UserResponse:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        users = UserRepository(session)
        audit_repo = AuditRepository(session)

        user = users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        user = users.reset_password(user, password_hash=hash_password(payload.new_password))
        audit_repo.create(
            actor_type="admin",
            actor_id="admin",
            action="user.password_reset",
            resource_type="user",
            resource_id=user.id,
            workspace_id=user.workspace_id,
            details={"email": user.email},
        )
        return _to_user_response(user)


@router.get("/me/workspace", response_model=WorkspaceInfoResponse)
def current_workspace_info(request: Request, workspace: Workspace = Depends(get_current_workspace)) -> WorkspaceInfoResponse:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        ws_repo = WorkspaceRepository(session)
        usage_repo = UsageRepository(session)
        current = ws_repo.get_by_id(workspace.id)
        if not current:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        return _workspace_info(usage_repo, current)


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(request: Request, limit: int = 20, workspace: Workspace = Depends(get_current_workspace)) -> JobListResponse:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        repo = JobRepository(session)
        jobs = repo.list_recent(workspace_id=workspace.id, limit=min(100, max(1, limit)))
        return JobListResponse(items=[_to_job_response(request, job) for job in jobs])


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    request: Request,
    file: UploadFile = File(...),
    workspace: Workspace = Depends(get_current_workspace),
) -> JobResponse:
    app_settings = request.app.state.settings
    storage = request.app.state.storage

    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required.")

    extension = Path(file.filename).suffix.lower()
    if extension not in app_settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported file extension: {extension}")

    job_id = str(uuid4())
    workspace_input_dir = app_settings.input_dir / workspace.id
    workspace_input_dir.mkdir(parents=True, exist_ok=True)
    input_path = workspace_input_dir / f"{job_id}{extension}"

    with input_path.open("wb") as output_file:
        shutil.copyfileobj(file.file, output_file)

    size = input_path.stat().st_size
    if size == 0:
        input_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if size > app_settings.max_upload_bytes:
        input_path.unlink(missing_ok=True)
        max_mb = app_settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"File exceeds {max_mb}MB limit.")

    try:
        input_reference = storage.stage_upload_file(
            workspace_id=workspace.id,
            job_id=job_id,
            extension=extension,
            local_source_path=input_path,
        )
    except StorageError as exc:
        input_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to persist uploaded file: {exc}",
        ) from exc

    period = period_start_utc()

    session_factory = request.app.state.session_factory
    job: Job | None = None
    try:
        with session_factory() as session:
            ws_repo = WorkspaceRepository(session)
            job_repo = JobRepository(session)
            audit_repo = AuditRepository(session)

            current_workspace = ws_repo.get_by_id(workspace.id)
            if not current_workspace:
                raise HTTPException(status_code=404, detail="Workspace not found.")
            if not current_workspace.is_active:
                raise HTTPException(status_code=403, detail="Workspace is inactive. Contact support.")
            if not is_processing_allowed_for_billing_status(current_workspace.billing_status):
                audit_repo.create(
                    actor_type="workspace_api_key",
                    actor_id=current_workspace.api_key_prefix,
                    action="job.rejected_billing",
                    resource_type="workspace",
                    resource_id=current_workspace.id,
                    workspace_id=current_workspace.id,
                    details={"billing_status": current_workspace.billing_status.value},
                )
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail=(
                        f"Workspace billing status is {current_workspace.billing_status.value}. "
                        "Processing is temporarily disabled."
                    ),
                )

            job, current_jobs = job_repo.create_job_with_quota_reservation(
                job=Job(
                    id=job_id,
                    workspace_id=current_workspace.id,
                    original_filename=Path(file.filename).name,
                    input_path=input_reference,
                    output_path=None,
                    status=JobStatus.QUEUED,
                    error_message=None,
                ),
                workspace_id=current_workspace.id,
                period_start=period,
                monthly_job_limit=current_workspace.monthly_job_limit,
            )
            if not job:
                audit_repo.create(
                    actor_type="workspace_api_key",
                    actor_id=current_workspace.api_key_prefix,
                    action="job.rejected_quota",
                    resource_type="workspace",
                    resource_id=current_workspace.id,
                    workspace_id=current_workspace.id,
                    details={
                        "period_start": str(period),
                        "current_jobs": current_jobs,
                        "monthly_job_limit": current_workspace.monthly_job_limit,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Workspace monthly job limit reached ({current_workspace.monthly_job_limit}). "
                        "Upgrade plan or wait for next billing cycle."
                    ),
                )

            audit_repo.create(
                actor_type="workspace_api_key",
                actor_id=current_workspace.api_key_prefix,
                action="job.created",
                resource_type="job",
                resource_id=job.id,
                workspace_id=current_workspace.id,
                details={
                    "filename": job.original_filename,
                    "size_bytes": size,
                    "period_start": str(period),
                    "remaining_jobs": max(0, current_workspace.monthly_job_limit - current_jobs),
                },
            )
    except HTTPException:
        if not job:
            storage.delete_reference(input_reference)
        raise
    except Exception:
        if not job:
            storage.delete_reference(input_reference)
        raise

    try:
        request.app.state.job_dispatcher.enqueue(job.id)
    except Exception as exc:
        with session_factory() as session:
            job_repo = JobRepository(session)
            audit_repo = AuditRepository(session)
            job_repo.update_status(
                job.id,
                status=JobStatus.FAILED,
                error_message=f"Dispatch failed: {exc}",
            )
            audit_repo.create(
                actor_type="system",
                actor_id="api",
                action="job.dispatch_failed",
                resource_type="job",
                resource_id=job.id,
                workspace_id=job.workspace_id,
                details={"error": str(exc)},
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Job was created but dispatch to worker failed.",
        ) from exc

    return _to_job_response(request, job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(request: Request, job_id: str, workspace: Workspace = Depends(get_current_workspace)) -> JobResponse:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        repo = JobRepository(session)
        job = repo.get_job(job_id, workspace_id=workspace.id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    return _to_job_response(request, job)


@router.get("/jobs/{job_id}/download", name="download_job_result")
def download_job_result(
    request: Request,
    job_id: str,
    workspace: Workspace = Depends(get_current_workspace),
) -> Response:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        repo = JobRepository(session)
        job = repo.get_job(job_id, workspace_id=workspace.id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if job.status != JobStatus.COMPLETED or not job.output_path:
        raise HTTPException(status_code=409, detail="Job is not completed yet.")

    app_settings = request.app.state.settings
    storage = request.app.state.storage
    download_name = f"{Path(job.original_filename).stem}_fixed.pdf"

    try:
        signed_url = storage.generate_download_url(
            job.output_path,
            download_name=download_name,
            expires_seconds=app_settings.storage_signed_url_ttl_seconds,
        )
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not generate download URL: {exc}",
        ) from exc

    if signed_url:
        return RedirectResponse(url=signed_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    output_path = storage.resolve_local_path(job.output_path)
    if not output_path or not output_path.exists():
        raise HTTPException(status_code=404, detail="Output file missing on server.")

    return FileResponse(path=output_path, media_type="application/pdf", filename=download_name)


@router.post("/workspaces", response_model=WorkspaceCreateResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreateRequest,
    request: Request,
    _: None = Depends(require_admin),
) -> WorkspaceCreateResponse:
    api_key = generate_api_key()
    limit = resolve_monthly_limit(payload.plan_name, payload.monthly_job_limit)

    session_factory = request.app.state.session_factory
    with session_factory() as session:
        repo = WorkspaceRepository(session)
        audit_repo = AuditRepository(session)

        existing = repo.get_by_name(payload.name)
        if existing:
            raise HTTPException(status_code=409, detail="Workspace name already exists.")

        workspace = repo.create(
            Workspace(
                id=str(uuid4()),
                name=payload.name,
                api_key_hash=hash_api_key(api_key),
                api_key_prefix=key_prefix(api_key),
                plan_name=payload.plan_name,
                monthly_job_limit=limit,
                billing_status=BillingStatus.ACTIVE,
                is_active=True,
            )
        )

        audit_repo.create(
            actor_type="admin",
            actor_id="admin",
            action="workspace.created",
            resource_type="workspace",
            resource_id=workspace.id,
            workspace_id=workspace.id,
            details={
                "name": workspace.name,
                "plan_name": workspace.plan_name,
                "monthly_job_limit": workspace.monthly_job_limit,
                "api_key_prefix": workspace.api_key_prefix,
            },
        )

    return WorkspaceCreateResponse(
        id=workspace.id,
        name=workspace.name,
        plan_name=workspace.plan_name,
        monthly_job_limit=workspace.monthly_job_limit,
        api_key=api_key,
        api_key_prefix=workspace.api_key_prefix,
        created_at=workspace.created_at,
    )


@router.get("/workspaces", response_model=list[WorkspaceInfoResponse])
def list_workspaces(request: Request, _: None = Depends(require_admin)) -> list[WorkspaceInfoResponse]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        ws_repo = WorkspaceRepository(session)
        usage_repo = UsageRepository(session)
        rows = ws_repo.list_all(limit=200)
        return [_workspace_info(usage_repo, workspace) for workspace in rows]


@router.patch("/workspaces/{workspace_id}/plan", response_model=WorkspaceInfoResponse)
def update_workspace_plan(
    workspace_id: str,
    payload: WorkspacePlanUpdateRequest,
    request: Request,
    _: None = Depends(require_admin),
) -> WorkspaceInfoResponse:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        ws_repo = WorkspaceRepository(session)
        usage_repo = UsageRepository(session)
        audit_repo = AuditRepository(session)

        workspace = ws_repo.get_by_id(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found.")

        previous = {
            "plan_name": workspace.plan_name,
            "monthly_job_limit": workspace.monthly_job_limit,
            "billing_status": workspace.billing_status.value,
        }

        _, limit = resolve_limit_for_update(
            current_plan_name=workspace.plan_name,
            current_monthly_limit=workspace.monthly_job_limit,
            incoming_plan_name=payload.plan_name,
            incoming_monthly_limit=payload.monthly_job_limit,
        )
        ws_repo.update_plan(
            workspace=workspace,
            plan_name=payload.plan_name,
            monthly_job_limit=limit,
            billing_status=payload.billing_status,
            stripe_customer_id=payload.stripe_customer_id,
            stripe_subscription_id=payload.stripe_subscription_id,
        )

        audit_repo.create(
            actor_type="admin",
            actor_id="admin",
            action="workspace.plan_updated",
            resource_type="workspace",
            resource_id=workspace.id,
            workspace_id=workspace.id,
            details={
                "previous": previous,
                "new": {
                    "plan_name": workspace.plan_name,
                    "monthly_job_limit": workspace.monthly_job_limit,
                    "billing_status": workspace.billing_status.value,
                },
            },
        )

        return _workspace_info(usage_repo, workspace)


@router.post("/billing/webhook/stripe", response_model=BillingWebhookResponse)
async def stripe_billing_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> BillingWebhookResponse:
    raw_payload = await request.body()

    try:
        verify_stripe_signature(
            payload=raw_payload,
            header_value=stripe_signature,
            secret=settings.billing_webhook_secret,
            tolerance_seconds=settings.stripe_webhook_tolerance_seconds,
        )
    except StripeSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    try:
        payload = normalize_billing_payload(raw_payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    session_factory = request.app.state.session_factory
    with session_factory() as session:
        billing_repo = BillingRepository(session)
        ws_repo = WorkspaceRepository(session)
        audit_repo = AuditRepository(session)
        resolved_workspace = _resolve_workspace_for_billing_payload(ws_repo, payload)

        existing = billing_repo.get_by_provider_event_id(payload.provider_event_id)
        if existing and existing.status in {BillingEventStatus.PROCESSED, BillingEventStatus.IGNORED}:
            workspace = resolved_workspace
            return BillingWebhookResponse(
                provider_event_id=payload.provider_event_id,
                status="duplicate_ignored",
                workspace_id=workspace.id if workspace else None,
                plan_name=workspace.plan_name if workspace else None,
                monthly_job_limit=workspace.monthly_job_limit if workspace else None,
            )

        event = billing_repo.create_event(
            provider="stripe",
            provider_event_id=payload.provider_event_id,
            event_type=payload.event_type,
            workspace_id=resolved_workspace.id if resolved_workspace else payload.workspace_id,
            payload=payload.model_dump(),
        )

        workspace = resolved_workspace
        if not workspace:
            billing_repo.mark_processed(
                event,
                status=BillingEventStatus.FAILED,
                error_message="Workspace not found for billing event.",
            )
            audit_repo.create(
                actor_type="billing_webhook",
                actor_id="stripe",
                action="billing.webhook_failed",
                resource_type="billing_event",
                resource_id=event.provider_event_id,
                workspace_id=None,
                details={"reason": "workspace_not_found"},
            )
            raise HTTPException(status_code=404, detail="Workspace not found.")

        previous = {
            "plan_name": workspace.plan_name,
            "monthly_job_limit": workspace.monthly_job_limit,
            "billing_status": workspace.billing_status.value,
        }
        plan_name, limit = resolve_limit_for_update(
            current_plan_name=workspace.plan_name,
            current_monthly_limit=workspace.monthly_job_limit,
            incoming_plan_name=payload.plan_name,
            incoming_monthly_limit=payload.monthly_job_limit,
        )

        ws_repo.update_plan(
            workspace=workspace,
            plan_name=plan_name,
            monthly_job_limit=limit,
            billing_status=payload.billing_status,
            stripe_customer_id=payload.stripe_customer_id or workspace.stripe_customer_id,
            stripe_subscription_id=payload.stripe_subscription_id or workspace.stripe_subscription_id,
        )

        billing_repo.mark_processed(event, status=BillingEventStatus.PROCESSED)
        audit_repo.create(
            actor_type="billing_webhook",
            actor_id="stripe",
            action="billing.plan_synced",
            resource_type="workspace",
            resource_id=workspace.id,
            workspace_id=workspace.id,
            details={
                "provider_event_id": payload.provider_event_id,
                "event_type": payload.event_type,
                "previous": previous,
                "new": {
                    "plan_name": workspace.plan_name,
                    "monthly_job_limit": workspace.monthly_job_limit,
                    "billing_status": workspace.billing_status.value,
                },
            },
        )

        return BillingWebhookResponse(
            provider_event_id=payload.provider_event_id,
            status="processed",
            workspace_id=workspace.id,
            plan_name=workspace.plan_name,
            monthly_job_limit=workspace.monthly_job_limit,
        )


@router.get("/me/audit/logs", response_model=AuditLogListResponse)
def list_my_audit_logs(
    request: Request,
    workspace: Workspace = Depends(get_current_workspace),
    limit: int = Query(default=50, ge=1, le=500),
) -> AuditLogListResponse:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        repo = AuditRepository(session)
        rows = repo.list_recent(limit=limit, workspace_id=workspace.id)
        return AuditLogListResponse(items=[_audit_to_response(row) for row in rows])


@router.get("/audit/logs", response_model=AuditLogListResponse)
def list_audit_logs(
    request: Request,
    _: None = Depends(require_admin),
    workspace_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> AuditLogListResponse:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        repo = AuditRepository(session)
        rows = repo.list_recent(limit=limit, workspace_id=workspace_id)
        return AuditLogListResponse(items=[_audit_to_response(row) for row in rows])


@router.get("/billing/events", response_model=BillingEventListResponse)
def list_billing_events(
    request: Request,
    _: None = Depends(require_admin),
    workspace_id: str | None = Query(default=None),
    status_filter: BillingEventStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=1000),
) -> BillingEventListResponse:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        repo = BillingRepository(session)
        rows = repo.list_recent(limit=limit, workspace_id=workspace_id, status=status_filter)
        return BillingEventListResponse(items=[_billing_event_to_response(row) for row in rows])
