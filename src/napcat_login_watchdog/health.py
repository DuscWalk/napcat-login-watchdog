from __future__ import annotations

import json
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


@dataclass(frozen=True, slots=True)
class HealthReport:
    status: str
    reasons: list[str]


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
    if any(marker in recent_logs for marker in OFFLINE_LOG_MARKERS):
        reasons.append("NapCat offline/login-expired marker found")
    if any(marker in recent_logs for marker in MANUAL_LOGIN_LOG_MARKERS):
        reasons.append("NapCat login requires QR/manual verification")
    return HealthReport(status="unhealthy" if reasons else "healthy", reasons=reasons)


def decide_status_email(
    state: dict[str, object],
    report: HealthReport,
    *,
    send_recovery: bool,
) -> str | None:
    previous_status = state.get("status")
    if report.status == "unhealthy" and previous_status != "unhealthy":
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
    result = subprocess.run(
        ["ss", "-H", "-tnp"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        errors="replace",
    )
    return onebot_connection_from_ss(result.stdout or "", config.host, config.port)
