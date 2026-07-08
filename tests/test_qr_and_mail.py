from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from napcat_login_watchdog.config import WatchdogConfig
from napcat_login_watchdog.mail import build_email_message
from napcat_login_watchdog.qr import find_fresh_qr, qr_click_token_from_path


def test_find_fresh_qr_prefers_explicit_path(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit.png"
    globbed = tmp_path / "nested" / "qrcode.png"
    globbed.parent.mkdir()
    explicit.write_bytes(b"explicit")
    globbed.write_bytes(b"globbed")

    config = WatchdogConfig(
        qr_path=str(explicit),
        qr_glob=str(tmp_path / "**" / "qrcode.png"),
        qr_max_age_seconds=120,
    )

    assert find_fresh_qr(config, now=explicit.stat().st_mtime + 1) == explicit


def test_build_email_attaches_qr_and_omits_secret(tmp_path: Path) -> None:
    qr = tmp_path / "qrcode.png"
    qr.write_bytes(b"fake-png")
    config = WatchdogConfig(
        smtp_user="sender@qq.com",
        smtp_password="secret-code",
        alert_email_from="sender@qq.com",
        alert_email_to=["admin@example.com"],
    )

    message = build_email_message(
        config,
        subject="[napcat-watchdog] NapCat login may be offline [qr:abc123]",
        body="NapCat needs QR login.",
        qr_path=qr,
    )

    raw = message.as_string()
    assert "secret-code" not in raw
    assert "napcat-login-qrcode.png" in raw


def test_build_email_uses_click_url_when_configured() -> None:
    config = WatchdogConfig(
        smtp_user="sender@qq.com",
        smtp_password="secret-code",
        alert_email_from="sender@qq.com",
        alert_email_to=["admin@example.com"],
        click_public_base_url="https://bot.example.com/base/",
        click_path_prefix="/qr",
    )

    message = build_email_message(
        config,
        subject="[napcat-watchdog] NapCat login may be offline [qr:abc123]",
        body="NapCat needs QR login.",
    )

    raw = message.as_string()
    assert "secret-code" not in raw
    assert "https://bot.example.com/base/qr/abc123" in raw
    assert "mailto:" not in raw


def test_build_email_falls_back_to_mailto_button() -> None:
    config = WatchdogConfig(
        smtp_user="sender@qq.com",
        smtp_password="secret-code",
        alert_email_from="sender@qq.com",
        alert_email_to=["admin@example.com"],
    )

    message = build_email_message(
        config,
        subject="[napcat-watchdog] NapCat login may be offline [qr:abc123]",
        body="NapCat needs QR login.",
    )

    html = next(part for part in message.walk() if part.get_content_type() == "text/html")
    href_start = html.get_content().index('href="') + len('href="')
    href_end = html.get_content().index('"', href_start)
    parsed = urlparse(unescape(html.get_content()[href_start:href_end]))
    query = parse_qs(parsed.query)

    assert parsed.scheme == "mailto"
    assert parsed.path == "sender@qq.com"
    assert query["body"] == ["qr\n"]


def test_qr_click_token_from_path_matches_configured_prefix() -> None:
    config = WatchdogConfig(click_path_prefix="/watchdog/qr")

    assert qr_click_token_from_path(config, "/watchdog/qr/abc-123?utm=mail") == "abc-123"
    assert qr_click_token_from_path(config, "/wrong/abc-123") == ""
    assert qr_click_token_from_path(config, "/watchdog/qr/abc-123/extra") == ""
