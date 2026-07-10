from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(slots=True)
class WatchdogConfig:
    bot_service: str = "qq-rolebot.service"
    napcat_service: str = "napcat.service"
    service_check_mode: str = "systemd"
    bot_check_command: str = ""
    napcat_check_command: str = ""
    host: str = "127.0.0.1"
    port: int = 8080
    require_onebot_connection: bool = True
    onebot_connection_check: str = "ss"
    require_onebot_http_api: bool = False
    onebot_http_api_base: str = ""
    onebot_http_api_token: str = ""
    onebot_http_api_timeout_seconds: int = 5
    log_window_minutes: int = 10
    log_command: str = ""
    state_path: str = "/opt/napcat-login-watchdog/state.json"
    send_recovery: bool = True
    offline_alert_repeat_seconds: int = 0
    qr_path: str = ""
    qr_glob: str = "/root/Napcat/**/cache/qrcode.png"
    qr_max_age_seconds: int = 120
    qr_refresh_command: str = "systemctl restart napcat.service"
    qr_refresh_wait_seconds: int = 15
    reply_enabled: bool = False
    reply_allowed_senders: list[str] = field(default_factory=list)
    reply_keywords: list[str] = field(default_factory=lambda: ["qr", "qrcode", "二维码", "扫码", "登录"])
    click_public_base_url: str = ""
    click_host: str = "127.0.0.1"
    click_port: int = 18081
    click_path_prefix: str = "/watchdog/qr"
    click_token_ttl_seconds: int = 86400
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 465
    smtp_ssl: bool = True
    smtp_starttls: bool = True
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email_from: str = ""
    alert_email_to: list[str] = field(default_factory=list)
    imap_host: str = "imap.qq.com"
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""
    qr_reply_cooldown_seconds: int = 60


def bool_env(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def int_env(value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def csv_env(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def normalize_path_prefix(value: str | None) -> str:
    prefix = (value or "/watchdog/qr").strip() or "/watchdog/qr"
    if not prefix.startswith("/"):
        prefix = f"/{prefix}"
    return prefix.rstrip("/") or "/watchdog/qr"


def load_config(env: Mapping[str, str]) -> WatchdogConfig:
    smtp_user = env.get("SMTP_USER", "")
    return WatchdogConfig(
        bot_service=env.get("WATCHDOG_BOT_SERVICE", "qq-rolebot.service"),
        napcat_service=env.get("WATCHDOG_NAPCAT_SERVICE", "napcat.service"),
        service_check_mode=env.get("WATCHDOG_SERVICE_CHECK_MODE", "systemd").strip().lower(),
        bot_check_command=env.get("WATCHDOG_BOT_CHECK_COMMAND", ""),
        napcat_check_command=env.get("WATCHDOG_NAPCAT_CHECK_COMMAND", ""),
        host=env.get("WATCHDOG_HOST", "127.0.0.1"),
        port=int_env(env.get("WATCHDOG_PORT"), 8080),
        require_onebot_connection=bool_env(env.get("WATCHDOG_REQUIRE_ONEBOT_CONNECTION"), True),
        onebot_connection_check=env.get("WATCHDOG_ONEBOT_CONNECTION_CHECK", "ss").strip().lower(),
        require_onebot_http_api=bool_env(env.get("WATCHDOG_REQUIRE_ONEBOT_HTTP_API"), False),
        onebot_http_api_base=env.get("WATCHDOG_ONEBOT_HTTP_API_BASE", "").rstrip("/"),
        onebot_http_api_token=env.get("WATCHDOG_ONEBOT_HTTP_API_TOKEN", ""),
        onebot_http_api_timeout_seconds=int_env(
            env.get("WATCHDOG_ONEBOT_HTTP_API_TIMEOUT_SECONDS"),
            5,
        ),
        log_window_minutes=int_env(env.get("WATCHDOG_LOG_WINDOW_MINUTES"), 10),
        log_command=env.get("WATCHDOG_LOG_COMMAND", ""),
        state_path=env.get("WATCHDOG_STATE_PATH", "/opt/napcat-login-watchdog/state.json"),
        send_recovery=bool_env(env.get("WATCHDOG_SEND_RECOVERY"), True),
        offline_alert_repeat_seconds=int_env(
            env.get("WATCHDOG_OFFLINE_ALERT_REPEAT_SECONDS"),
            0,
        ),
        qr_path=env.get("WATCHDOG_QR_PATH", ""),
        qr_glob=env.get("WATCHDOG_QR_GLOB", "/root/Napcat/**/cache/qrcode.png"),
        qr_max_age_seconds=int_env(env.get("WATCHDOG_QR_MAX_AGE_SECONDS"), 120),
        qr_refresh_command=env.get("WATCHDOG_QR_REFRESH_COMMAND", "systemctl restart napcat.service"),
        qr_refresh_wait_seconds=int_env(env.get("WATCHDOG_QR_REFRESH_WAIT_SECONDS"), 15),
        reply_enabled=bool_env(env.get("WATCHDOG_REPLY_ENABLED"), False),
        reply_allowed_senders=csv_env(env.get("WATCHDOG_REPLY_ALLOWED_SENDERS")),
        reply_keywords=csv_env(env.get("WATCHDOG_REPLY_KEYWORDS"))
        or ["qr", "qrcode", "二维码", "扫码", "登录"],
        click_public_base_url=env.get("WATCHDOG_CLICK_PUBLIC_BASE_URL", ""),
        click_host=env.get("WATCHDOG_CLICK_HOST", "127.0.0.1"),
        click_port=int_env(env.get("WATCHDOG_CLICK_PORT"), 18081),
        click_path_prefix=normalize_path_prefix(env.get("WATCHDOG_CLICK_PATH_PREFIX")),
        click_token_ttl_seconds=int_env(env.get("WATCHDOG_CLICK_TOKEN_TTL_SECONDS"), 86400),
        smtp_host=env.get("SMTP_HOST", "smtp.qq.com"),
        smtp_port=int_env(env.get("SMTP_PORT"), 465),
        smtp_ssl=bool_env(env.get("SMTP_SSL"), True),
        smtp_starttls=bool_env(env.get("SMTP_STARTTLS"), True),
        smtp_user=smtp_user,
        smtp_password=env.get("SMTP_PASSWORD", ""),
        alert_email_from=env.get("ALERT_EMAIL_FROM", smtp_user),
        alert_email_to=csv_env(env.get("ALERT_EMAIL_TO")),
        imap_host=env.get("IMAP_HOST", "imap.qq.com"),
        imap_port=int_env(env.get("IMAP_PORT"), 993),
        imap_user=env.get("IMAP_USER", smtp_user),
        imap_password=env.get("IMAP_PASSWORD", env.get("SMTP_PASSWORD", "")),
        qr_reply_cooldown_seconds=int_env(env.get("WATCHDOG_QR_REPLY_COOLDOWN_SECONDS"), 60),
    )
