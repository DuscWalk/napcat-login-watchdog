from __future__ import annotations

from dataclasses import dataclass

from napcat_login_watchdog.config import WatchdogConfig
from napcat_login_watchdog.mail import email_configured, imap_configured
from napcat_login_watchdog.qr import find_fresh_qr
from napcat_login_watchdog.runner import (
    WatchdogDependencies,
    onebot_socket_healthy,
    service_is_healthy,
)


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    name: str
    status: str
    detail: str


def run_doctor(config: WatchdogConfig, deps: WatchdogDependencies) -> list[DiagnosticResult]:
    results: list[DiagnosticResult] = []

    bot_ok = service_is_healthy(
        config,
        deps,
        service=config.bot_service,
        command=config.bot_check_command,
    )
    results.append(
        DiagnosticResult(
            "bot service",
            "ok" if bot_ok else "fail",
            f"{config.bot_service} is {'healthy' if bot_ok else 'not healthy'}",
        )
    )

    napcat_ok = service_is_healthy(
        config,
        deps,
        service=config.napcat_service,
        command=config.napcat_check_command,
    )
    results.append(
        DiagnosticResult(
            "napcat service",
            "ok" if napcat_ok else "fail",
            f"{config.napcat_service} is {'healthy' if napcat_ok else 'not healthy'}",
        )
    )

    tcp_ok = deps.tcp_connect(config.host, config.port)
    results.append(
        DiagnosticResult(
            "tcp port",
            "ok" if tcp_ok else "fail",
            f"{config.host}:{config.port} is {'reachable' if tcp_ok else 'not reachable'}",
        )
    )

    if config.require_onebot_connection:
        socket_ok = onebot_socket_healthy(config, deps)
        results.append(
            DiagnosticResult(
                "OneBot reverse WebSocket",
                "ok" if socket_ok else "fail",
                "connection check passed" if socket_ok else "connection check failed",
            )
        )
    else:
        results.append(
            DiagnosticResult(
                "OneBot reverse WebSocket",
                "skip",
                "WATCHDOG_REQUIRE_ONEBOT_CONNECTION=false",
            )
        )

    if config.require_onebot_http_api:
        http_ok = deps.onebot_http_api_healthy(config)
        results.append(
            DiagnosticResult(
                "OneBot HTTP API",
                "ok" if http_ok else "fail",
                "status check passed" if http_ok else "status check failed",
            )
        )
    else:
        results.append(
            DiagnosticResult(
                "OneBot HTTP API",
                "skip",
                "WATCHDOG_REQUIRE_ONEBOT_HTTP_API=false",
            )
        )

    logs = deps.read_recent_logs(config)
    results.append(
        DiagnosticResult(
            "logs",
            "ok",
            f"read {len(logs)} characters from configured log source",
        )
    )

    qr = find_fresh_qr(config, now=deps.now())
    results.append(
        DiagnosticResult(
            "QR image",
            "ok" if qr is not None else "warn",
            str(qr) if qr is not None else "no fresh QR image currently available",
        )
    )

    if email_configured(config):
        smtp_ok = deps.smtp_login_ok(config)
        results.append(
            DiagnosticResult(
                "SMTP",
                "ok" if smtp_ok else "fail",
                "login succeeded" if smtp_ok else "login failed",
            )
        )
    else:
        results.append(DiagnosticResult("SMTP", "fail", "alert email is not fully configured"))

    if config.reply_enabled:
        if imap_configured(config):
            imap_ok = deps.imap_login_ok(config)
            results.append(
                DiagnosticResult(
                    "IMAP",
                    "ok" if imap_ok else "fail",
                    "login succeeded" if imap_ok else "login failed",
                )
            )
        else:
            results.append(DiagnosticResult("IMAP", "fail", "reply refresh is enabled but IMAP is not configured"))
    else:
        results.append(DiagnosticResult("IMAP", "skip", "WATCHDOG_REPLY_ENABLED=false"))

    return results

