from __future__ import annotations

import secrets
import shlex
import socket
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from napcat_login_watchdog.config import WatchdogConfig
from napcat_login_watchdog.health import (
    HealthReport,
    decide_status_email,
    evaluate_health,
    onebot_connected,
    onebot_http_api_healthy,
)
from napcat_login_watchdog.mail import (
    MailReply,
    build_email_message,
    email_configured,
    imap_configured,
    imap_login_ok,
    is_authorized_reply,
    read_imap_replies,
    send_smtp_email,
    smtp_login_ok,
)
from napcat_login_watchdog.qr import find_fresh_qr
from napcat_login_watchdog.state import load_state, save_state


@dataclass(frozen=True, slots=True)
class WatchdogDependencies:
    service_is_active: Callable[[str], bool]
    tcp_connect: Callable[[str, int], bool]
    read_recent_logs: Callable[[WatchdogConfig], str]
    send_email: Callable[[WatchdogConfig, EmailMessage], None]
    read_replies: Callable[[WatchdogConfig], list[MailReply]]
    run_refresh_command: Callable[[WatchdogConfig], int]
    now: Callable[[], float]
    token_factory: Callable[[], str]
    sleep: Callable[[float], None]
    log: Callable[[str], None]
    run_check_command: Callable[[str], int] = lambda command: 1
    onebot_connected: Callable[[WatchdogConfig], bool] = lambda config: True
    onebot_http_api_healthy: Callable[[WatchdogConfig], bool] = lambda config: True
    smtp_login_ok: Callable[[WatchdogConfig], bool] = lambda config: False
    imap_login_ok: Callable[[WatchdogConfig], bool] = lambda config: False
    reply_type: type[MailReply] = MailReply


def offline_body(report: HealthReport, qr_path: Path | None) -> str:
    lines = [
        "NapCat account may be offline.",
        "",
        "Reasons:",
        *(f"- {reason}" for reason in report.reasons),
        "",
    ]
    if qr_path is not None:
        lines.append("A fresh login QR code is attached as napcat-login-qrcode.png.")
    else:
        lines.append("No fresh QR code was available. Reply to this email to request a new one.")
    lines.append("Do not forward this email because the QR code grants login access.")
    return "\n".join(lines)


def recovery_body() -> str:
    return "NapCat account appears healthy again."


def reply_qr_body(qr_path: Path | None) -> str:
    if qr_path is not None:
        return "Fresh NapCat login QR code is attached as napcat-login-qrcode.png."
    return "The server tried to refresh the QR code, but no fresh QR image was available."


def send_if_configured(
    config: WatchdogConfig,
    deps: WatchdogDependencies,
    *,
    subject: str,
    body: str,
    qr_path: Path | None = None,
) -> bool:
    if not email_configured(config):
        deps.log("watchdog email is not configured; skipping alert")
        return False
    deps.send_email(config, build_email_message(config, subject=subject, body=body, qr_path=qr_path))
    return True


def fresh_qr_after_optional_refresh(
    config: WatchdogConfig,
    deps: WatchdogDependencies,
    *,
    force_refresh: bool,
) -> Path | None:
    qr = None if force_refresh else find_fresh_qr(config, now=deps.now())
    if qr is not None:
        return qr
    if config.qr_refresh_command:
        deps.run_refresh_command(config)
        if config.qr_refresh_wait_seconds > 0:
            deps.sleep(config.qr_refresh_wait_seconds)
        qr = find_fresh_qr(config, now=deps.now())
    return qr


def service_is_healthy(
    config: WatchdogConfig,
    deps: WatchdogDependencies,
    *,
    service: str,
    command: str,
) -> bool:
    if config.service_check_mode == "none":
        return True
    if config.service_check_mode == "command":
        return bool(command) and deps.run_check_command(command) == 0
    if config.service_check_mode == "systemd":
        return deps.service_is_active(service)
    return False


def onebot_socket_healthy(config: WatchdogConfig, deps: WatchdogDependencies) -> bool:
    if config.onebot_connection_check == "none":
        return True
    return deps.onebot_connected(config)


def run_watchdog(config: WatchdogConfig, deps: WatchdogDependencies) -> HealthReport:
    state_path = Path(config.state_path)
    state = load_state(state_path)
    report = evaluate_health(
        config,
        bot_active=service_is_healthy(
            config,
            deps,
            service=config.bot_service,
            command=config.bot_check_command,
        ),
        napcat_active=service_is_healthy(
            config,
            deps,
            service=config.napcat_service,
            command=config.napcat_check_command,
        ),
        tcp_ok=deps.tcp_connect(config.host, config.port),
        onebot_connected=onebot_socket_healthy(config, deps),
        onebot_http_api_healthy=deps.onebot_http_api_healthy(config),
        recent_logs=deps.read_recent_logs(config),
    )

    email_kind = decide_status_email(state, report, send_recovery=config.send_recovery)
    token = str(state.get("active_qr_token") or deps.token_factory())
    if email_kind == "offline" and config.click_public_base_url:
        token = deps.token_factory()
    if report.status == "unhealthy":
        state["active_qr_token"] = token
        if email_kind == "offline":
            state["active_qr_token_timestamp"] = int(deps.now())
        else:
            state.setdefault("active_qr_token_timestamp", int(deps.now()))

    if email_kind == "offline":
        qr_path = fresh_qr_after_optional_refresh(config, deps, force_refresh=False)
        if send_if_configured(
            config,
            deps,
            subject=f"[napcat-watchdog] NapCat login may be offline [qr:{token}]",
            body=offline_body(report, qr_path),
            qr_path=qr_path,
        ):
            state["last_alert_timestamp"] = int(deps.now())
            if qr_path is not None:
                state["last_qr_path"] = str(qr_path)
                state["last_qr_timestamp"] = int(deps.now())
    elif email_kind == "recovery":
        if send_if_configured(
            config,
            deps,
            subject="[napcat-watchdog] NapCat login recovered",
            body=recovery_body(),
        ):
            state["last_recovery_timestamp"] = int(deps.now())

    handled = [str(uid) for uid in state.get("handled_reply_uids", [])]
    if config.reply_enabled and imap_configured(config):
        for reply in deps.read_replies(config):
            if not is_authorized_reply(config, reply, state):
                continue
            last_reply = int(state.get("last_qr_reply_timestamp") or 0)
            if deps.now() - last_reply < config.qr_reply_cooldown_seconds:
                continue
            qr_path = fresh_qr_after_optional_refresh(config, deps, force_refresh=True)
            if send_if_configured(
                config,
                deps,
                subject=f"[napcat-watchdog] Fresh NapCat login QR [qr:{token}]",
                body=reply_qr_body(qr_path),
                qr_path=qr_path,
            ):
                handled.append(reply.uid)
                state["handled_reply_uids"] = sorted(set(handled))
                state["last_qr_reply_timestamp"] = int(deps.now())

    state["status"] = report.status
    state["last_failure_reasons"] = report.reasons
    state["last_checked_timestamp"] = int(deps.now())
    save_state(state_path, state)
    return report


def systemd_service_is_active(service: str) -> bool:
    return (
        subprocess.run(
            ["systemctl", "is-active", "--quiet", service],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def tcp_connect(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def read_recent_logs(config: WatchdogConfig) -> str:
    since = f"-{config.log_window_minutes} minutes"
    if config.log_command:
        command = config.log_command.format(
            minutes=config.log_window_minutes,
            since=since,
            bot_service=config.bot_service,
            napcat_service=config.napcat_service,
        )
        result = subprocess.run(
            command,
            check=False,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            errors="replace",
        )
        return result.stdout or ""

    chunks: list[str] = []
    for unit in (config.napcat_service, config.bot_service):
        result = subprocess.run(
            ["journalctl", "-u", unit, "--since", since, "--no-pager", "-l"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            errors="replace",
        )
        chunks.append(result.stdout or "")
    return "\n".join(chunks)


def run_refresh_command(config: WatchdogConfig) -> int:
    if not config.qr_refresh_command:
        return 0
    return subprocess.run(
        shlex.split(config.qr_refresh_command),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode


def run_check_command(command: str) -> int:
    return subprocess.run(
        command,
        check=False,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode


def default_dependencies() -> WatchdogDependencies:
    return WatchdogDependencies(
        service_is_active=systemd_service_is_active,
        tcp_connect=tcp_connect,
        read_recent_logs=read_recent_logs,
        send_email=send_smtp_email,
        read_replies=read_imap_replies,
        run_refresh_command=run_refresh_command,
        run_check_command=run_check_command,
        now=time.time,
        token_factory=lambda: secrets.token_urlsafe(18),
        sleep=time.sleep,
        log=lambda message: print(message),
        onebot_connected=onebot_connected,
        onebot_http_api_healthy=onebot_http_api_healthy,
        smtp_login_ok=smtp_login_ok,
        imap_login_ok=imap_login_ok,
    )
