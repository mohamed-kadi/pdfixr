from __future__ import annotations

from fastapi import Header, HTTPException, Request, status

from .config import settings
from .models import UserRole
from .repository import UserRepository, WorkspaceRepository
from .security import extract_bearer_token, hash_api_key, verify_auth_token


def get_current_workspace(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    session_factory = request.app.state.session_factory

    with session_factory() as session:
        repo = WorkspaceRepository(session)

        bearer = extract_bearer_token(authorization)
        if bearer:
            try:
                claims = verify_auth_token(
                    bearer,
                    secret=settings.auth_token_secret,
                    expected_kind=None,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid auth token: {exc}",
                ) from exc

            kind = claims.get("kind")
            if kind == "workspace":
                workspace_id = claims.get("workspace_id")
                if not isinstance(workspace_id, str) or not workspace_id:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Workspace token missing workspace_id.")

                workspace = repo.get_by_id(workspace_id)
                if not workspace or not workspace.is_active:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Workspace token is no longer valid.")
                return workspace

            if kind == "user":
                role = claims.get("role")
                workspace_id = claims.get("workspace_id")
                if role != UserRole.CLIENT.value:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="User has no workspace processing access.",
                    )
                if not isinstance(workspace_id, str) or not workspace_id:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User token missing workspace_id.")

                workspace = repo.get_by_id(workspace_id)
                if not workspace or not workspace.is_active:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Workspace linked to user is inactive.")
                return workspace

            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token kind is not valid for workspace access.")

        if x_api_key:
            workspace = repo.get_by_api_key_hash(hash_api_key(x_api_key))
            if not workspace:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
            return workspace

        if settings.require_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing auth credentials. Provide Authorization bearer token or X-API-Key header.",
            )

        # Local/dev fallback workspace when API keys are optional.
        workspace = repo.get_by_name(settings.default_workspace_name)
        if not workspace:
            raise HTTPException(status_code=500, detail="Default workspace not initialized.")
        return workspace


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    bearer = extract_bearer_token(authorization)
    if not bearer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

    try:
        claims = verify_auth_token(
            bearer,
            secret=settings.auth_token_secret,
            expected_kind="user",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid user token: {exc}") from exc

    user_id = claims.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User token missing user_id.")

    session_factory = request.app.state.session_factory
    with session_factory() as session:
        users = UserRepository(session)
        user = users.get_by_id(user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive or missing.")
        return user


def require_admin(
    request: Request,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    bearer = extract_bearer_token(authorization)
    if bearer:
        try:
            claims = verify_auth_token(
                bearer,
                secret=settings.auth_token_secret,
                expected_kind=None,
            )
            kind = claims.get("kind")
            if kind == "admin":
                return
            if kind == "user":
                if claims.get("role") == UserRole.ADMIN.value:
                    return
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required.")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token kind is not valid for admin access.")
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid admin token: {exc}",
            ) from exc

    if not x_admin_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key.")
