from __future__ import annotations

import json
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4

from ..config import Settings


@dataclass(frozen=True)
class PasswordResetEmail:
    to_email: str
    reset_url: str
    expires_at: datetime


class PasswordResetMailer:
    def send_password_reset_email(self, message: PasswordResetEmail) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class JobStatusEmail:
    to_email: str
    workspace_id: str
    job_id: str
    original_filename: str
    status: str
    error_message: str | None = None


class JobNotificationMailer:
    def send_job_status_email(self, message: JobStatusEmail) -> None:
        raise NotImplementedError


class FilePasswordResetMailer(PasswordResetMailer):
    def __init__(self, *, outbox_dir: Path, from_email: str) -> None:
        self.outbox_dir = outbox_dir
        self.from_email = from_email

    def send_password_reset_email(self, message: PasswordResetEmail) -> None:
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "type": "password_reset",
            "from": self.from_email,
            "to": message.to_email,
            "subject": "Reset your PDF portal password",
            "expires_at": message.expires_at.isoformat(),
            "reset_url": message.reset_url,
            "text": (
                "You requested a password reset for your PDF portal account.\n\n"
                f"Reset link: {message.reset_url}\n"
                f"This link expires at: {message.expires_at.isoformat()}\n\n"
                "If you did not request this, ignore this email."
            ),
        }

        filename = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex}.json"
        path = self.outbox_dir / filename
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class FileJobNotificationMailer(JobNotificationMailer):
    def __init__(self, *, outbox_dir: Path, from_email: str) -> None:
        self.outbox_dir = outbox_dir
        self.from_email = from_email

    def send_job_status_email(self, message: JobStatusEmail) -> None:
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

        subject = (
            "Your PDF is ready for download"
            if message.status == "completed"
            else "Your PDF processing job needs attention"
        )
        status_line = "completed successfully" if message.status == "completed" else "failed"
        error_line = (
            f"\nError: {message.error_message}" if message.error_message and message.status != "completed" else ""
        )

        payload = {
            "type": "job_status",
            "from": self.from_email,
            "to": message.to_email,
            "subject": subject,
            "workspace_id": message.workspace_id,
            "job_id": message.job_id,
            "original_filename": message.original_filename,
            "status": message.status,
            "error_message": message.error_message,
            "text": (
                f"Your job {message.job_id} for file '{message.original_filename}' has {status_line}.\n"
                f"Workspace: {message.workspace_id}\n"
                "Sign in to your portal to review and download the result."
                f"{error_line}"
            ),
        }

        filename = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex}.json"
        path = self.outbox_dir / filename
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class SmtpPasswordResetMailer(PasswordResetMailer):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        use_tls: bool,
        from_email: str,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.from_email = from_email

    def send_password_reset_email(self, message: PasswordResetEmail) -> None:
        email_message = EmailMessage()
        email_message["From"] = self.from_email
        email_message["To"] = message.to_email
        email_message["Subject"] = "Reset your PDF portal password"
        email_message.set_content(
            "You requested a password reset for your PDF portal account.\n\n"
            f"Reset link: {message.reset_url}\n"
            f"This link expires at: {message.expires_at.isoformat()}\n\n"
            "If you did not request this, ignore this email."
        )

        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            smtp.ehlo()
            if self.use_tls:
                context = ssl.create_default_context()
                smtp.starttls(context=context)
                smtp.ehlo()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(email_message)


class SmtpJobNotificationMailer(JobNotificationMailer):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        use_tls: bool,
        from_email: str,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.from_email = from_email

    def send_job_status_email(self, message: JobStatusEmail) -> None:
        subject = (
            "Your PDF is ready for download"
            if message.status == "completed"
            else "Your PDF processing job needs attention"
        )
        status_line = "completed successfully" if message.status == "completed" else "failed"
        error_line = (
            f"\nError: {message.error_message}" if message.error_message and message.status != "completed" else ""
        )
        body = (
            f"Your job {message.job_id} for file '{message.original_filename}' has {status_line}.\n"
            f"Workspace: {message.workspace_id}\n"
            "Sign in to your portal to review and download the result."
            f"{error_line}"
        )

        email_message = EmailMessage()
        email_message["From"] = self.from_email
        email_message["To"] = message.to_email
        email_message["Subject"] = subject
        email_message.set_content(body)

        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            smtp.ehlo()
            if self.use_tls:
                context = ssl.create_default_context()
                smtp.starttls(context=context)
                smtp.ehlo()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(email_message)


def build_password_reset_mailer(settings: Settings) -> PasswordResetMailer:
    if settings.email_delivery_mode == "smtp" and settings.smtp_host:
        return SmtpPasswordResetMailer(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            from_email=settings.smtp_from_email,
        )

    return FilePasswordResetMailer(
        outbox_dir=settings.email_outbox_dir,
        from_email=settings.smtp_from_email,
    )


def build_job_notification_mailer(settings: Settings) -> JobNotificationMailer:
    if settings.email_delivery_mode == "smtp" and settings.smtp_host:
        return SmtpJobNotificationMailer(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            from_email=settings.smtp_from_email,
        )

    return FileJobNotificationMailer(
        outbox_dir=settings.email_outbox_dir,
        from_email=settings.smtp_from_email,
    )
