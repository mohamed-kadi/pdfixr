from __future__ import annotations

import json
from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    AuditLog,
    BillingEvent,
    BillingEventStatus,
    BillingStatus,
    Job,
    JobStatus,
    User,
    UserRole,
    Workspace,
    WorkspaceUsage,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_job_with_quota_reservation(
        self,
        *,
        job: Job,
        workspace_id: str,
        period_start: date,
        monthly_job_limit: int,
    ) -> tuple[Job | None, int]:
        usage_repo = UsageRepository(self.session)
        usage = usage_repo.get_or_create(workspace_id=workspace_id, period_start=period_start)

        # Atomic reservation: only increment usage if current count is still below the plan limit.
        reserve_stmt = (
            update(WorkspaceUsage)
            .where(WorkspaceUsage.id == usage.id, WorkspaceUsage.jobs_count < monthly_job_limit)
            .values(
                jobs_count=WorkspaceUsage.jobs_count + 1,
                updated_at=utc_now(),
            )
        )
        reserved = self.session.execute(reserve_stmt)
        if int(reserved.rowcount or 0) != 1:
            self.session.rollback()
            current_count = usage_repo.count_for_period(workspace_id=workspace_id, period_start=period_start)
            return None, current_count

        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        current_count = usage_repo.count_for_period(workspace_id=workspace_id, period_start=period_start)
        return job, current_count

    def get_job(self, job_id: str, *, workspace_id: str | None = None) -> Job | None:
        job = self.session.get(Job, job_id)
        if not job:
            return None
        if workspace_id and job.workspace_id != workspace_id:
            return None
        return job

    def list_recent(self, *, workspace_id: str, limit: int = 20) -> list[Job]:
        stmt: Select[tuple[Job]] = (
            select(Job)
            .where(Job.workspace_id == workspace_id)
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def update_status(
        self,
        job_id: str,
        *,
        status: JobStatus,
        output_path: str | None = None,
        error_message: str | None = None,
    ) -> Job | None:
        job = self.session.get(Job, job_id)
        if not job:
            return None

        job.status = status
        job.updated_at = utc_now()
        if output_path is not None:
            job.output_path = output_path
        job.error_message = error_message

        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job


class WorkspaceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, workspace: Workspace) -> Workspace:
        self.session.add(workspace)
        self.session.commit()
        self.session.refresh(workspace)
        return workspace

    def list_all(self, limit: int = 100) -> list[Workspace]:
        stmt = select(Workspace).order_by(Workspace.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt).all())

    def list_active(self) -> list[Workspace]:
        stmt = select(Workspace).where(Workspace.is_active.is_(True))
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, workspace_id: str) -> Workspace | None:
        return self.session.get(Workspace, workspace_id)

    def get_by_name(self, name: str) -> Workspace | None:
        stmt = select(Workspace).where(Workspace.name == name)
        return self.session.scalar(stmt)

    def get_by_stripe_customer_id(self, stripe_customer_id: str) -> Workspace | None:
        stmt = select(Workspace).where(Workspace.stripe_customer_id == stripe_customer_id)
        return self.session.scalar(stmt)

    def get_by_stripe_subscription_id(self, stripe_subscription_id: str) -> Workspace | None:
        stmt = select(Workspace).where(Workspace.stripe_subscription_id == stripe_subscription_id)
        return self.session.scalar(stmt)

    def get_by_api_key_hash(self, api_key_hash: str) -> Workspace | None:
        stmt = select(Workspace).where(Workspace.api_key_hash == api_key_hash, Workspace.is_active.is_(True))
        return self.session.scalar(stmt)

    def upsert_default(
        self,
        *,
        name: str,
        api_key_hash: str,
        api_key_prefix: str,
        plan_name: str,
        monthly_job_limit: int,
    ) -> Workspace:
        workspace = self.get_by_name(name)
        if workspace:
            workspace.api_key_hash = api_key_hash
            workspace.api_key_prefix = api_key_prefix
            workspace.plan_name = plan_name
            workspace.monthly_job_limit = monthly_job_limit
            workspace.billing_status = BillingStatus.ACTIVE
            workspace.is_active = True
            self.session.add(workspace)
            self.session.commit()
            self.session.refresh(workspace)
            return workspace

        workspace = Workspace(
            id=str(uuid4()),
            name=name,
            api_key_hash=api_key_hash,
            api_key_prefix=api_key_prefix,
            plan_name=plan_name,
            monthly_job_limit=monthly_job_limit,
            billing_status=BillingStatus.ACTIVE,
            is_active=True,
        )
        self.session.add(workspace)
        self.session.commit()
        self.session.refresh(workspace)
        return workspace

    def update_plan(
        self,
        *,
        workspace: Workspace,
        plan_name: str,
        monthly_job_limit: int,
        billing_status: BillingStatus,
        stripe_customer_id: str | None,
        stripe_subscription_id: str | None,
        is_active: bool | None = None,
    ) -> Workspace:
        workspace.plan_name = plan_name
        workspace.monthly_job_limit = monthly_job_limit
        workspace.billing_status = billing_status
        workspace.stripe_customer_id = stripe_customer_id
        workspace.stripe_subscription_id = stripe_subscription_id
        if is_active is not None:
            workspace.is_active = is_active
        workspace.updated_at = utc_now()

        self.session.add(workspace)
        self.session.commit()
        self.session.refresh(workspace)
        return workspace


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, user: User) -> User:
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def get_by_id(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        lowered = email.strip().lower()
        stmt = select(User).where(func.lower(User.email) == lowered)
        return self.session.scalar(stmt)

    def list_all(self, limit: int = 200) -> list[User]:
        stmt = select(User).order_by(User.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt).all())

    def list_active_clients_for_workspace(self, *, workspace_id: str) -> list[User]:
        stmt = (
            select(User)
            .where(
                User.workspace_id == workspace_id,
                User.role == UserRole.CLIENT,
                User.is_active.is_(True),
            )
            .order_by(User.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())

    def count_active_admins(self) -> int:
        stmt = select(func.count(User.id)).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        count = self.session.scalar(stmt)
        return int(count or 0)

    def upsert_default_user(
        self,
        *,
        email: str,
        password_hash: str,
        role: UserRole,
        workspace_id: str | None,
    ) -> User:
        user = self.get_by_email(email)
        if user:
            user.password_hash = password_hash
            user.role = role
            user.workspace_id = workspace_id
            user.is_active = True
            user.updated_at = utc_now()
            self.session.add(user)
            self.session.commit()
            self.session.refresh(user)
            return user

        user = User(
            id=str(uuid4()),
            email=email.strip().lower(),
            password_hash=password_hash,
            role=role,
            workspace_id=workspace_id,
            is_active=True,
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def update(
        self,
        user: User,
        *,
        role: UserRole,
        workspace_id: str | None,
        is_active: bool,
    ) -> User:
        user.role = role
        user.workspace_id = workspace_id
        user.is_active = is_active
        user.updated_at = utc_now()
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def reset_password(self, user: User, *, password_hash: str) -> User:
        user.password_hash = password_hash
        user.updated_at = utc_now()
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def set_active(self, user: User, *, is_active: bool) -> User:
        user.is_active = is_active
        user.updated_at = utc_now()
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user


class UsageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create(self, *, workspace_id: str, period_start: date) -> WorkspaceUsage:
        stmt = select(WorkspaceUsage).where(
            WorkspaceUsage.workspace_id == workspace_id,
            WorkspaceUsage.period_start == period_start,
        )
        row = self.session.scalar(stmt)
        if row:
            return row

        row = WorkspaceUsage(workspace_id=workspace_id, period_start=period_start, jobs_count=0)
        self.session.add(row)
        try:
            self.session.commit()
            self.session.refresh(row)
            return row
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(stmt)
            if existing:
                return existing
            raise

    def get_for_workspace(self, *, workspace_id: str, period_start: date) -> WorkspaceUsage | None:
        stmt = select(WorkspaceUsage).where(
            WorkspaceUsage.workspace_id == workspace_id,
            WorkspaceUsage.period_start == period_start,
        )
        return self.session.scalar(stmt)

    def count_for_period(self, *, workspace_id: str, period_start: date) -> int:
        stmt = select(WorkspaceUsage.jobs_count).where(
            WorkspaceUsage.workspace_id == workspace_id,
            WorkspaceUsage.period_start == period_start,
        )
        count = self.session.scalar(stmt)
        return int(count or 0)

    def ensure_period_rows(self, *, workspace_ids: list[str], period_start: date) -> None:
        for workspace_id in workspace_ids:
            self.get_or_create(workspace_id=workspace_id, period_start=period_start)

    def cleanup_before(self, *, cutoff: date) -> int:
        stmt = delete(WorkspaceUsage).where(WorkspaceUsage.period_start < cutoff)
        result = self.session.execute(stmt)
        self.session.commit()
        return int(result.rowcount or 0)


class BillingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_provider_event_id(self, provider_event_id: str) -> BillingEvent | None:
        stmt = select(BillingEvent).where(BillingEvent.provider_event_id == provider_event_id)
        return self.session.scalar(stmt)

    def create_event(
        self,
        *,
        provider: str,
        provider_event_id: str,
        event_type: str,
        workspace_id: str | None,
        payload: dict,
    ) -> BillingEvent:
        event = BillingEvent(
            id=str(uuid4()),
            provider=provider,
            provider_event_id=provider_event_id,
            event_type=event_type,
            workspace_id=workspace_id,
            status=BillingEventStatus.RECEIVED,
            raw_payload=json.dumps(payload, separators=(",", ":"), ensure_ascii=True),
        )
        self.session.add(event)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.get_by_provider_event_id(provider_event_id)
            if not existing:
                raise
            return existing
        self.session.refresh(event)
        return event

    def mark_processed(self, event: BillingEvent, *, status: BillingEventStatus, error_message: str | None = None) -> BillingEvent:
        event.status = status
        event.error_message = error_message
        event.processed_at = utc_now()
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def list_recent(
        self,
        *,
        limit: int = 100,
        workspace_id: str | None = None,
        status: BillingEventStatus | None = None,
    ) -> list[BillingEvent]:
        stmt = select(BillingEvent).order_by(BillingEvent.created_at.desc()).limit(limit)
        if workspace_id:
            stmt = stmt.where(BillingEvent.workspace_id == workspace_id)
        if status:
            stmt = stmt.where(BillingEvent.status == status)
        return list(self.session.scalars(stmt).all())


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        actor_type: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        workspace_id: str | None = None,
        details: dict | None = None,
    ) -> AuditLog:
        row = AuditLog(
            workspace_id=workspace_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details_json=json.dumps(details or {}, separators=(",", ":"), ensure_ascii=True),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def list_recent(self, *, limit: int = 100, workspace_id: str | None = None) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        if workspace_id:
            stmt = stmt.where(AuditLog.workspace_id == workspace_id)
        return list(self.session.scalars(stmt).all())
