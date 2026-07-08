from __future__ import annotations

import html
import http.server
import secrets
from dataclasses import dataclass
from pathlib import Path

from napcat_login_watchdog.config import WatchdogConfig
from napcat_login_watchdog.qr import qr_click_token_from_path
from napcat_login_watchdog.runner import (
    WatchdogDependencies,
    fresh_qr_after_optional_refresh,
    reply_qr_body,
    send_if_configured,
)
from napcat_login_watchdog.state import load_state, save_state


@dataclass(frozen=True, slots=True)
class QrClickResult:
    status: str
    email_sent: bool


def handle_qr_click(
    config: WatchdogConfig,
    token: str,
    deps: WatchdogDependencies,
) -> QrClickResult:
    state_path = Path(config.state_path)
    state = load_state(state_path)
    active_token = str(state.get("active_qr_token") or "")
    if not token or not active_token or not secrets.compare_digest(token, active_token):
        return QrClickResult(status="invalid", email_sent=False)

    now = int(deps.now())
    token_timestamp = int(
        state.get("active_qr_token_timestamp") or state.get("last_alert_timestamp") or 0
    )
    if (
        config.click_token_ttl_seconds > 0
        and token_timestamp > 0
        and now - token_timestamp > config.click_token_ttl_seconds
    ):
        return QrClickResult(status="expired", email_sent=False)

    last_click = int(state.get("last_qr_click_timestamp") or 0)
    if last_click > 0 and now - last_click < config.qr_reply_cooldown_seconds:
        return QrClickResult(status="throttled", email_sent=False)

    qr_path = fresh_qr_after_optional_refresh(config, deps, force_refresh=True)
    sent = send_if_configured(
        config,
        deps,
        subject=f"[napcat-watchdog] Fresh NapCat login QR [qr:{active_token}]",
        body=reply_qr_body(qr_path),
        qr_path=qr_path,
    )
    if sent:
        state["last_qr_click_timestamp"] = now
        save_state(state_path, state)
        return QrClickResult(status="sent", email_sent=True)
    return QrClickResult(status="failed", email_sent=False)


def qr_click_http_status(result: QrClickResult, *, path_matched: bool) -> int:
    if not path_matched:
        return 404
    return {
        "sent": 200,
        "throttled": 429,
        "expired": 410,
        "invalid": 403,
        "failed": 500,
    }.get(result.status, 500)


def qr_click_response_html(result: QrClickResult, *, path_matched: bool) -> bytes:
    if not path_matched:
        title = "Link not found"
        message = "This watchdog link was not recognized."
    else:
        title, message = {
            "sent": (
                "QR email requested",
                "A fresh NapCat login QR email has been sent to the administrator mailbox.",
            ),
            "throttled": (
                "Already requested",
                "A QR email was requested recently. Please check the mailbox first.",
            ),
            "expired": (
                "Link expired",
                "This watchdog link has expired. Reply to the alert email with qr.",
            ),
            "invalid": (
                "Invalid link",
                "This watchdog link is invalid or no longer active.",
            ),
        }.get(
            result.status,
            (
                "Request failed",
                "The server could not send the QR email. Please check watchdog logs.",
            ),
        )
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title>"
        "</head><body>"
        f"<h1>{html.escape(title)}</h1>"
        f"<p>{html.escape(message)}</p>"
        "</body></html>"
    ).encode("utf-8")


def serve_qr_click_webhook(config: WatchdogConfig, deps: WatchdogDependencies) -> None:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            token = qr_click_token_from_path(config, self.path)
            path_matched = bool(token)
            result = (
                handle_qr_click(config, token, deps)
                if path_matched
                else QrClickResult(status="invalid", email_sent=False)
            )
            payload = qr_click_response_html(result, path_matched=path_matched)
            self.send_response(qr_click_http_status(result, path_matched=path_matched))
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            deps.log(f"watchdog click request from {self.client_address[0]}")

    with http.server.ThreadingHTTPServer((config.click_host, config.click_port), Handler) as server:
        deps.log(f"watchdog click server listening on {config.click_host}:{config.click_port}")
        server.serve_forever()
