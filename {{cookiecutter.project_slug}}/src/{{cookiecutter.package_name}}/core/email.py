"""Outbound email: template rendering, an SMTP backend and a console fallback.

Emails are rendered from the Jinja2 templates in ``email-templates/`` (an HTML
body plus a plain-text alternative). With ``EMAILS_ENABLED=false`` (the
default) messages are logged instead of delivered, so local development never
needs an SMTP server.
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr
from pathlib import Path
from typing import Any, Protocol

import structlog
from fastapi.concurrency import run_in_threadpool
from jinja2 import Environment, FileSystemLoader, select_autoescape

from {{ cookiecutter.package_name }}.core.config import settings

logger = structlog.get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "email-templates"
_templates = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """A rendered email, ready for any backend to deliver."""

    to: str
    subject: str
    html: str
    text: str


class EmailBackend(Protocol):
    """Delivers rendered emails; implementations decide the transport."""

    async def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailBackend:
    """Logs emails instead of delivering them — the local-development default."""

    async def send(self, message: EmailMessage) -> None:
        logger.info(
            "email.console",
            to=message.to,
            subject=message.subject,
            body=message.text,
        )


class SmtpEmailBackend:
    """Delivers emails over SMTP using the ``SMTP_*`` settings."""

    async def send(self, message: EmailMessage) -> None:
        # smtplib is blocking; keep the handshake and delivery off the event loop.
        await run_in_threadpool(self._send_sync, message)

    @staticmethod
    def _send_sync(message: EmailMessage) -> None:
        host = settings.smtp_host
        if host is None:  # pragma: no cover - get_email_backend guards this
            raise RuntimeError("SMTP_HOST is not configured")
        mime = MimeMessage()
        mime["From"] = formataddr(
            (settings.project_name, settings.emails_from_email or settings.contact_email)
        )
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        mime.add_alternative(message.html, subtype="html")
        with smtplib.SMTP(host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_tls:
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password or "")
            smtp.send_message(mime)
        logger.info("email.sent", to=message.to, subject=message.subject)


def get_email_backend() -> EmailBackend:
    """The configured backend: SMTP when enabled, otherwise the console logger."""
    if settings.emails_enabled and settings.smtp_host:
        return SmtpEmailBackend()
    return ConsoleEmailBackend()


def render_email(template: str, **context: Any) -> tuple[str, str]:
    """Render the ``.html`` and ``.txt`` variants of ``template``.

    Returns the HTML and plain-text bodies, in that order.
    """
    html = _templates.get_template(f"{template}.html").render(**context)
    text = _templates.get_template(f"{template}.txt").render(**context)
    return html, text
