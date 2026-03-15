from __future__ import annotations

from .config import settings
from .models import UserRole
from .repository import UserRepository, WorkspaceRepository
from .security import hash_api_key, hash_password, key_prefix


def ensure_default_workspace(session_factory):
    with session_factory() as session:
        repo = WorkspaceRepository(session)
        return repo.upsert_default(
            name=settings.default_workspace_name,
            api_key_hash=hash_api_key(settings.default_workspace_api_key),
            api_key_prefix=key_prefix(settings.default_workspace_api_key),
            plan_name=settings.default_workspace_plan,
            monthly_job_limit=settings.default_workspace_monthly_limit,
        )


def ensure_default_users(session_factory, *, workspace_id: str) -> None:
    with session_factory() as session:
        users = UserRepository(session)
        users.upsert_default_user(
            email=settings.default_admin_email,
            password_hash=hash_password(settings.default_admin_password),
            role=UserRole.ADMIN,
            workspace_id=None,
        )
        users.upsert_default_user(
            email=settings.default_client_email,
            password_hash=hash_password(settings.default_client_password),
            role=UserRole.CLIENT,
            workspace_id=workspace_id,
        )


def ensure_bootstrap(session_factory) -> None:
    workspace = ensure_default_workspace(session_factory)
    ensure_default_users(session_factory, workspace_id=workspace.id)
