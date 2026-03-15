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
