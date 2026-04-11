from __future__ import annotations

import asyncio
import base64
import html
import logging
import re
import smtplib
import traceback
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from .common.services import background_internal_task
from .core.models import Email

logger = logging.getLogger("backbone.email")

APP_TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates"
APP_EMAIL_ROOT = Path(__file__).resolve().parents[1] / "email_templates"
FRAMEWORK_TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates"


def _build_email_environment() -> Environment:
    loader = ChoiceLoader(
        [
            FileSystemLoader(str(APP_EMAIL_ROOT)),
            FileSystemLoader(str(APP_TEMPLATE_ROOT)),
            FileSystemLoader(str(FRAMEWORK_TEMPLATE_ROOT)),
        ]
    )
    return Environment(loader=loader, autoescape=select_autoescape(["html", "xml"]))


EMAIL_ENVIRONMENT = _build_email_environment()


def _render_template(template_name: str, context: Dict[str, Any]) -> str:
    template = EMAIL_ENVIRONMENT.get_template(template_name)
    return template.render(**context)


def _strip_html(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _html_to_text_for_pdf(raw_html: str) -> str:
    value = raw_html or ""
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</(p|div|h1|h2|h3|h4|h5|h6)>", "\n\n", value)
    value = re.sub(r"(?i)<li[^>]*>", "- ", value)
    value = re.sub(r"(?i)</li>", "\n", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _wrap_line(text: str, font_name: str, font_size: int, max_width: float) -> List[str]:
    if not text.strip():
        return [""]

    words = text.split()
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _render_pdf_sync(rendered_html: str) -> bytes:
    content = _html_to_text_for_pdf(rendered_html)

    out = BytesIO()
    pdf = canvas.Canvas(out, pagesize=A4)
    page_width, page_height = A4

    margin = 16 * mm
    line_height = 14
    font_name = "Helvetica"
    font_size = 11
    max_width = page_width - (2 * margin)

    y = page_height - margin
    pdf.setFont(font_name, font_size)

    paragraphs = content.split("\n")
    for para in paragraphs:
        wrapped_lines = _wrap_line(para, font_name, font_size, max_width)
        for line in wrapped_lines:
            if y <= margin:
                pdf.showPage()
                pdf.setFont(font_name, font_size)
                y = page_height - margin
            pdf.drawString(margin, y, line)
            y -= line_height
        y -= int(line_height / 2)

    pdf.save()
    return out.getvalue()


async def _render_pdf(html: str) -> bytes:
    return await asyncio.to_thread(_render_pdf_sync, html)


def _read_file_sync(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _build_mime_message(
    *,
    to_email: str,
    subject: str,
    html_body: str,
    plain_text_body: str,
    from_email: str,
    from_name: str,
    attachments: List[Tuple[str, bytes, str]],
) -> MIMEMultipart:
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid(domain=from_email.split("@")[-1] if "@" in from_email else None)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain_text_body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    for filename, data, content_type in attachments:
        part = MIMEApplication(data, Name=filename)
        part["Content-Disposition"] = f'attachment; filename="{filename}"'
        if content_type:
            part.replace_header("Content-Type", content_type)
        msg.attach(part)

    return msg


def _smtp_send_sync(message: MIMEMultipart) -> None:
    from .core.config import BackboneConfig
    settings = BackboneConfig.get_instance().config
    host_lower = (settings.EMAIL_HOST or "").lower()
    if "gmail" in host_lower and (not settings.EMAIL_USERNAME or not settings.EMAIL_PASSWORD):
        raise RuntimeError(
            "Gmail SMTP requires EMAIL_USERNAME and EMAIL_PASSWORD (use an App Password)."
        )

    if settings.EMAIL_USE_SSL:
        server = smtplib.SMTP_SSL(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=settings.EMAIL_TIMEOUT_SECONDS)
    else:
        server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=settings.EMAIL_TIMEOUT_SECONDS)

    try:
        server.ehlo()
        if settings.EMAIL_USE_TLS and not settings.EMAIL_USE_SSL:
            server.starttls()
            server.ehlo()
        if settings.EMAIL_USERNAME and settings.EMAIL_PASSWORD:
            server.login(settings.EMAIL_USERNAME, settings.EMAIL_PASSWORD)
        server.send_message(message)
    finally:
        server.quit()


class EmailSender:
    async def queue_email(
        self,
        *,
        to_email: str,
        subject: str,
        template_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        plain_text_body: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        pdf_attachments: Optional[List[Dict[str, Any]]] = None,
        max_retries: int = 3,
    ) -> Optional[str]:
        from .core.config import BackboneConfig
        settings = BackboneConfig.get_instance().config
        context = context or {}
        attachments = attachments or []
        pdf_attachments = pdf_attachments or []

        email_log = Email(
            to_email=to_email,
            subject=subject,
            template_name=template_name,
            context=context,
            plain_text_body=plain_text_body,
            attachments=attachments,
            pdf_attachments=pdf_attachments,
            from_email=settings.EMAIL_FROM_EMAIL,
            status="queued" if settings.EMAIL_ENABLED else "skipped",
            error_message=None if settings.EMAIL_ENABLED else "EMAIL_ENABLED is false.",
        )
        await email_log.insert()

        if not settings.EMAIL_ENABLED:
            return str(email_log.id)

        task_id = await background_internal_task(
            process_email_delivery_task,
            str(email_log.id),
            max_retries=max_retries,
        )
        if task_id is None:
            refreshed = await Email.get(str(email_log.id))
            if refreshed and refreshed.status == "queued":
                refreshed.status = "failed"
                refreshed.error_message = "Failed to enqueue email background task."
                await refreshed.save()
        return str(email_log.id)

    async def queue_registration_emails(self, *, to_email: str, full_name: str, login_url: str) -> Dict[str, Optional[str]]:
        from .core.config import BackboneConfig
        settings = BackboneConfig.get_instance().config
        base_context = {
            "full_name": full_name,
            "login_url": login_url,
            "support_email": settings.EMAIL_FROM_EMAIL,
            "current_year": datetime.now(timezone.utc).year,
        }

        welcome_id = await self.queue_email(
            to_email=to_email,
            subject="Welcome to Blogermenia",
            template_name="email/welcome_email.html",
            context=base_context,
        )

        welcome_pack_id = await self.queue_email(
            to_email=to_email,
            subject="Your Blogermenia welcome pack",
            template_name="email/welcome_pack_email.html",
            context=base_context,
            pdf_attachments=[
                {
                    "template_name": "email/pdf/welcome_packet.html",
                    "context": base_context,
                    "filename": "welcome-packet.pdf",
                    "content_type": "application/pdf",
                }
            ],
        )

        return {
            "welcome_email_log_id": welcome_id,
            "welcome_pack_email_log_id": welcome_pack_id,
        }


async def process_email_delivery_task(email_log_id: str) -> None:
    from .core.config import BackboneConfig
    settings = BackboneConfig.get_instance().config
    email_log = await Email.get(email_log_id)
    if not email_log:
        logger.warning("Email not found for id=%s", email_log_id)
        return

    if not settings.EMAIL_ENABLED:
        email_log.status = "skipped"
        email_log.error_message = "EMAIL_ENABLED is false."
        await email_log.save()
        return

    email_log.status = "processing"
    email_log.started_at = datetime.now(timezone.utc)
    email_log.attempt_count = (email_log.attempt_count or 0) + 1
    await email_log.save()

    try:
        context = dict(email_log.context or {})
        html_body = ""
        if email_log.template_name:
            html_body = _render_template(email_log.template_name, context)
        elif email_log.html_body:
            html_body = email_log.html_body
        else:
            raise ValueError("Email body is empty. Provide template_name or html_body.")

        plain_text_body = email_log.plain_text_body or _strip_html(html_body)

        built_attachments: List[Tuple[str, bytes, str]] = []
        for item in email_log.attachments or []:
            filename = str(item.get("filename") or "attachment.bin")
            content_type = str(item.get("content_type") or "application/octet-stream")
            if item.get("content_base64"):
                data = base64.b64decode(item["content_base64"])
            elif item.get("file_path"):
                data = await asyncio.to_thread(_read_file_sync, str(item["file_path"]))
            else:
                raise ValueError(f"Attachment {filename} missing both content_base64 and file_path.")
            built_attachments.append((filename, data, content_type))

        for pdf_item in email_log.pdf_attachments or []:
            pdf_template = str(pdf_item.get("template_name", "")).strip()
            if not pdf_template:
                raise ValueError("pdf_attachments[].template_name is required.")
            pdf_context = pdf_item.get("context") or context
            filename = str(pdf_item.get("filename") or "attachment.pdf")
            content_type = str(pdf_item.get("content_type") or "application/pdf")

            pdf_html = _render_template(pdf_template, pdf_context)
            pdf_bytes = await _render_pdf(pdf_html)
            built_attachments.append((filename, pdf_bytes, content_type))

        msg = _build_mime_message(
            to_email=email_log.to_email,
            subject=email_log.subject,
            html_body=html_body,
            plain_text_body=plain_text_body,
            from_email=settings.EMAIL_FROM_EMAIL,
            from_name=settings.EMAIL_FROM_NAME,
            attachments=built_attachments,
        )

        await asyncio.to_thread(_smtp_send_sync, msg)

        email_log.status = "sent"
        email_log.sent_at = datetime.now(timezone.utc)
        email_log.error_message = None
        email_log.error_traceback = None
        email_log.provider_message_id = msg.get("Message-ID")
        email_log.html_body = html_body
        await email_log.save()
    except smtplib.SMTPException as exc:
        logger.exception("Permanent SMTP failure for %s", email_log_id)
        email_log.status = "failed"
        email_log.error_message = str(exc)
        email_log.error_traceback = traceback.format_exc()
        await email_log.save()
        # SMTP failures such as auth/permission issues are generally permanent
        # until config changes; do not re-raise to avoid useless retries.
        return
    except Exception as exc:
        logger.exception("Email send failed for %s", email_log_id)
        email_log.status = "failed"
        email_log.error_message = str(exc)
        email_log.error_traceback = traceback.format_exc()
        await email_log.save()
        raise


email_sender = EmailSender()
