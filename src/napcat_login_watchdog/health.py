from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass

from napcat_login_watchdog.config import WatchdogConfig

OFFLINE_LOG_MARKERS = (
    "bot_offline",
    "KickedOffLine",
    "登录态已失效",
    "Login Error",
)

MANUAL_LOGIN_LOG_MARKERS = (
    "请扫描下面的二维码",
    "二维码已保存",
    "qrcode",
    "sms-verify-login",
)

HEALTHY_LOG_MARKERS = (
    "Bot ",
    "[message.",
)

_JOURNAL_TS = re.compile(
    r"^(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
)
_APP_TS = re.compile(
    r"(?P<month>\d{2})-(?P<day>\d{2})\s+"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
)
_MONTH_INDEX = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


@dataclass(frozen=True, slots=True)
class HealthReport:
    status: str
    reasons: list[str]


def _line_position(line: str, fallback_index: int) -> tuple[int, int, int, int, int, int]:
    journal = _JOURNAL_TS.search(line)
    if journal is not None:
        return (
            _MONTH_INDEX.get(journal.group("month"), 0),
            int(journal.group("day")),
            int(journal.group("hour")),
            int(journal.group("minute")),
            int(journal.group("second")),
            fallback_index,
        )
    app = _APP_TS.search(line)
    if app is not None:
        return (
            int(app.group("month")),
            int(app.group("day")),
            int(app.group("hour")),
            int(app.group("minute")),
            int(app.group("second")),
            fallback_index,
        )
    return (0, 0, 0, 0, 0, fallback_index)


def _latest_marker_position(logs: str, markers: tuple[str, ...]) -> tuple[int, int, int, int, int, int] | None:
    latest = None
    for index, line in enumerate(logs.splitlines()):
        if not any(marker in line for marker in markers):
            continue
        position = _line_position(line, index)
        if latest is None or position > latest:
            latest = position
    return latest


def log_markers_are_current(recent_logs: str, markers: tuple[str, ...]) -> bool:
    latest_marker = _latest_marker_position(recent_logs, markers)
    if latest_marker is None:
        return False
    latest_healthy = _latest_marker_position(recent_logs, HEALTHY_LOG_MARKERS)
    return latest_healthy is None or latest_marker > latest_healthy


def evaluate_health(
    config: WatchdogConfig,
    *,
    bot_active: bool,
    napcat_active: bool,
    tcp_ok: bool,
    onebot_connected: bool = True,
    onebot_http_api_healthy: bool = True,
    recent_logs: str,
) -> HealthReport:
    reasons: list[str] = []
    if not bot_active:
        reasons.append(f"{config.bot_service} is not active")
    if not napcat_active:
        reasons.append(f"{config.napcat_service} is not active")
    if not tcp_ok:
        reasons.append(f"{config.host}:{config.port} is not reachable")
    if config.require_onebot_connection and not onebot_connected:
        reasons.append("OneBot reverse WebSocket is not connected")
    if config.require_onebot_http_api and not onebot_http_api_healthy:
        reasons.append("OneBot HTTP API status check failed")
    if log_markers_are_current(recent_logs, OFFLINE_LOG_MARKERS):
        reasons.append("NapCat offline/login-expired marker found")
    if log_markers_are_current(recent_logs, MANUAL_LOGIN_LOG_MARKERS):
        reasons.append("NapCat login requires QR/manual verification")
    return HealthReport(status="unhealthy" if reasons else "healthy", reasons=reasons)


def decide_status_email(
    state: dict[str, object],
    report: HealthReport,
    *,
    send_recovery: bool,
    now: int | float | None = None,
    repeat_seconds: int = 0,
) -> str | None:
    previous_status = state.get("status")
    if report.status == "unhealthy" and previous_status != "unhealthy":
        return "offline"
    if (
        report.status == "unhealthy"
        and previous_status == "unhealthy"
        and repeat_seconds > 0
        and now is not None
    ):
        last_alert = int(state.get("last_alert_timestamp") or 0)
        if last_alert <= 0 or now - last_alert >= repeat_seconds:
            return "offline"
    if report.status == "healthy" and previous_status == "unhealthy" and send_recovery:
        return "recovery"
    return None


def endpoint_matches(endpoint: str, host: str, port: int) -> bool:
    endpoint = endpoint.strip("[]")
    if not endpoint.endswith(f":{port}"):
        return False
    if host in {"0.0.0.0", "::"}:
        return True
    return endpoint.startswith(f"{host}:") or endpoint.startswith(f"[{host}]:")


def onebot_connection_from_ss(output: str, host: str, port: int) -> bool:
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0] != "ESTAB":
            continue
        if endpoint_matches(parts[3], host, port) or endpoint_matches(parts[4], host, port):
            return True
    return False


def onebot_http_api_healthy_from_payloads(login_info: dict, status: dict) -> bool:
    if int(login_info.get("retcode", -1)) != 0:
        return False
    if int(status.get("retcode", -1)) != 0:
        return False
    data = status.get("data")
    return not (isinstance(data, dict) and data.get("online") is False)


def onebot_api_post(config: WatchdogConfig, action: str) -> dict:
    base = config.onebot_http_api_base.rstrip("/")
    if not base:
        raise ValueError("WATCHDOG_ONEBOT_HTTP_API_BASE is not configured")
    request = urllib.request.Request(
        f"{base}/{action.lstrip('/')}",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if config.onebot_http_api_token:
        request.add_header("Authorization", f"Bearer {config.onebot_http_api_token}")
    with urllib.request.urlopen(request, timeout=config.onebot_http_api_timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def onebot_http_api_healthy(config: WatchdogConfig) -> bool:
    if not config.require_onebot_http_api:
        return True
    try:
        return onebot_http_api_healthy_from_payloads(
            onebot_api_post(config, "get_login_info"),
            onebot_api_post(config, "get_status"),
        )
    except (
        OSError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
        urllib.error.URLError,
        urllib.error.HTTPError,
    ):
        return False


def onebot_connected(config: WatchdogConfig) -> bool:
    if config.onebot_connection_check == "none":
        return True
    if config.onebot_connection_check != "ss":
        return False
    result = subprocess.run(
        ["ss", "-H", "-tnp"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        errors="replace",
    )
    return onebot_connection_from_ss(result.stdout or "", config.host, config.port)
