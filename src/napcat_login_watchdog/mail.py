from __future__ import annotations

import email
import html
import imaplib
import smtplib
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import quote

from napcat_login_watchdog.config import WatchdogConfig, normalize_path_prefix


@dataclass(frozen=True, slots=True)
class MailReply:
    uid: str
    sender: str
    subject: str
    body: str


def email_configured(config: WatchdogConfig) -> bool:
    return bool(
        config.smtp_host
        and config.smtp_port
        and config.smtp_user
        and config.smtp_password
        and config.alert_email_from
        and config.alert_email_to
    )


def imap_configured(config: WatchdogConfig) -> bool:
    return bool(config.imap_host and config.imap_port and config.imap_user and config.imap_password)


def qr_token_from_subject(subject: str) -> str:
    marker = "[qr:"
    start = subject.find(marker)
    if start < 0:
        return ""
    start += len(marker)
    end = subject.find("]", start)
    if end < 0:
        return ""
    return subject[start:end].strip()


def qr_click_url(config: WatchdogConfig, subject: str) -> str | None:
    token = qr_token_from_subject(subject)
    if not token or not config.click_public_base_url:
        return None
    base_url = config.click_public_base_url.rstrip("/")
    path_prefix = normalize_path_prefix(config.click_path_prefix)
    return f"{base_url}{path_prefix}/{quote(token, safe='')}"


def qr_reply_mailto(address: str, subject: str) -> str:
    reply_subject = f"Re: {subject}"
    reply_body = "qr\n"
    return (
        f"mailto:{quote(address, safe='@.+-_')}"
        f"?subject={quote(reply_subject, safe='')}"
        f"&body={quote(reply_body, safe='')}"
    )


def plain_body_with_qr_link(config: WatchdogConfig, *, subject: str, body: str) -> str:
    url = qr_click_url(config, subject)
    if url is None:
        return body
    return "\n".join(
        [
            body.rstrip(),
            "",
            "Open this link to request a fresh NapCat login QR code:",
            url,
            "",
            "If the link does not work, reply to this email with qr.",
        ]
    )


def html_body_with_qr_button(config: WatchdogConfig, *, subject: str, body: str) -> str | None:
    url = qr_click_url(config, subject)
    fallback = "If the button does not work, reply to this email with <code>qr</code>."
    if url is None:
        if "[qr:" not in subject or not config.alert_email_from:
            return None
        url = qr_reply_mailto(config.alert_email_from, subject)
    escaped_body = html.escape(body).replace("\n", "<br>\n")
    return "\n".join(
        [
            "<!doctype html>",
            "<html>",
            "<body>",
            f"<p>{escaped_body}</p>",
            '<p><a style="display:inline-block;padding:10px 14px;'
            "background:#2563eb;color:#ffffff;text-decoration:none;"
            f'border-radius:6px" href="{html.escape(url, quote=True)}">'
            "获取新二维码</a></p>",
            f"<p>{fallback}</p>",
            "</body>",
            "</html>",
        ]
    )


def build_email_message(
    config: WatchdogConfig,
    *,
    subject: str,
    body: str,
    qr_path: Path | None = None,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = config.alert_email_from
    message["To"] = ", ".join(config.alert_email_to)
    message["Subject"] = subject
    message.set_content(plain_body_with_qr_link(config, subject=subject, body=body))
    html_body = html_body_with_qr_button(config, subject=subject, body=body)
    if html_body is not None:
        message.add_alternative(html_body, subtype="html")
    if qr_path is not None:
        message.add_attachment(
            qr_path.read_bytes(),
            maintype="image",
            subtype="png",
            filename="napcat-login-qrcode.png",
        )
    return message


def send_smtp_email(config: WatchdogConfig, message: EmailMessage) -> None:
    if config.smtp_ssl:
        with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=20) as smtp:
            smtp.login(config.smtp_user, config.smtp_password)
            smtp.send_message(message)
        return
    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20) as smtp:
        if config.smtp_starttls:
            smtp.starttls()
        smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(message)


def smtp_login_ok(config: WatchdogConfig) -> bool:
    if not email_configured(config):
        return False
    try:
        if config.smtp_ssl:
            with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=20) as smtp:
                smtp.login(config.smtp_user, config.smtp_password)
            return True
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20) as smtp:
            if config.smtp_starttls:
                smtp.starttls()
            smtp.login(config.smtp_user, config.smtp_password)
        return True
    except (OSError, smtplib.SMTPException):
        return False


def imap_login_ok(config: WatchdogConfig) -> bool:
    if not imap_configured(config):
        return False
    try:
        with imaplib.IMAP4_SSL(config.imap_host, config.imap_port) as mailbox:
            mailbox.login(config.imap_user, config.imap_password)
        return True
    except (OSError, imaplib.IMAP4.error):
        return False


def decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def message_body(message: email.message.Message) -> str:
    if message.is_multipart():
        parts = []
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = part.get_content_disposition()
            if disposition == "attachment" or content_type not in {"text/plain", "text/html"}:
                continue
            payload = part.get_payload(decode=True)
            if payload is not None:
                parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
        return "\n".join(parts)
    payload = message.get_payload(decode=True)
    if payload is None:
        return str(message.get_payload() or "")
    return payload.decode(message.get_content_charset() or "utf-8", errors="replace")


def read_imap_replies(config: WatchdogConfig) -> list[MailReply]:
    if not imap_configured(config):
        return []
    replies: list[MailReply] = []
    with imaplib.IMAP4_SSL(config.imap_host, config.imap_port) as mailbox:
        mailbox.login(config.imap_user, config.imap_password)
        mailbox.select("INBOX")
        status, data = mailbox.uid("search", None, "UNSEEN")
        if status != "OK" or not data:
            return []
        for uid_bytes in data[0].split()[-20:]:
            uid = uid_bytes.decode("ascii", errors="replace")
            status, fetched = mailbox.uid("fetch", uid_bytes, "(RFC822)")
            if status != "OK":
                continue
            for item in fetched:
                if not isinstance(item, tuple):
                    continue
                parsed = email.message_from_bytes(item[1])
                replies.append(
                    MailReply(
                        uid=uid,
                        sender=parseaddr(parsed.get("From", ""))[1],
                        subject=decode_header_value(parsed.get("Subject")),
                        body=message_body(parsed),
                    )
                )
    return replies


def is_authorized_reply(
    config: WatchdogConfig,
    reply: MailReply,
    state: dict[str, object],
) -> bool:
    handled = {str(uid) for uid in state.get("handled_reply_uids", [])}
    if reply.uid in handled:
        return False
    allowed = {sender.lower() for sender in config.reply_allowed_senders}
    if not allowed or reply.sender.lower() not in allowed:
        return False
    token = str(state.get("active_qr_token") or "")
    if token and f"[qr:{token}]" in reply.subject:
        return True
    searchable = f"{reply.subject}\n{reply.body}".lower()
    return any(keyword.lower() in searchable for keyword in config.reply_keywords)
