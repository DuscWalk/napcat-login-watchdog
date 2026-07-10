import json
from pathlib import Path

from napcat_login_watchdog.config import WatchdogConfig
from napcat_login_watchdog.runner import WatchdogDependencies, run_watchdog
from napcat_login_watchdog.webhook import QrClickResult, handle_qr_click


def test_run_watchdog_sends_offline_email_once_and_records_state(tmp_path: Path) -> None:
    qr = tmp_path / "qrcode.png"
    qr.write_bytes(b"fake-png")
    sent = []
    config = WatchdogConfig(
        state_path=str(tmp_path / "state.json"),
        qr_path=str(qr),
        smtp_user="sender@qq.com",
        smtp_password="smtp-code",
        alert_email_from="sender@qq.com",
        alert_email_to=["admin@example.com"],
    )
    deps = WatchdogDependencies(
        service_is_active=lambda service: service == "napcat.service",
        tcp_connect=lambda host, port: False,
        read_recent_logs=lambda cfg: "请扫描下面的二维码",
        send_email=lambda cfg, message: sent.append(message),
        read_replies=lambda cfg: [],
        run_refresh_command=lambda cfg: 0,
        now=lambda: 120.0,
        token_factory=lambda: "abc123",
        sleep=lambda seconds: None,
        log=lambda message: None,
    )

    first = run_watchdog(config, deps)
    second = run_watchdog(config, deps)

    assert first.status == "unhealthy"
    assert second.status == "unhealthy"
    assert len(sent) == 1
    state = json.loads(Path(config.state_path).read_text(encoding="utf-8"))
    assert state["status"] == "unhealthy"
    assert state["last_failure_reasons"]


def test_run_watchdog_repeats_offline_email_after_cooldown(tmp_path: Path) -> None:
    qr = tmp_path / "qrcode.png"
    qr.write_bytes(b"fake-png")
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"status":"unhealthy","last_alert_timestamp":100,"active_qr_token":"abc123"}',
        encoding="utf-8",
    )
    sent = []
    config = WatchdogConfig(
        state_path=str(state_path),
        qr_path=str(qr),
        offline_alert_repeat_seconds=300,
        smtp_user="sender@qq.com",
        smtp_password="smtp-code",
        alert_email_from="sender@qq.com",
        alert_email_to=["admin@example.com"],
    )
    deps = WatchdogDependencies(
        service_is_active=lambda service: service == "napcat.service",
        tcp_connect=lambda host, port: False,
        read_recent_logs=lambda cfg: "请扫描下面的二维码",
        send_email=lambda cfg, message: sent.append(message),
        read_replies=lambda cfg: [],
        run_refresh_command=lambda cfg: 0,
        now=lambda: 500.0,
        token_factory=lambda: "unused",
        sleep=lambda seconds: None,
        log=lambda message: None,
    )

    report = run_watchdog(config, deps)

    assert report.status == "unhealthy"
    assert len(sent) == 1
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["last_alert_timestamp"] == 500


def test_run_watchdog_can_skip_service_and_onebot_socket_checks(tmp_path: Path) -> None:
    sent = []
    config = WatchdogConfig(
        state_path=str(tmp_path / "state.json"),
        service_check_mode="none",
        onebot_connection_check="none",
        smtp_user="sender@qq.com",
        smtp_password="smtp-code",
        alert_email_from="sender@qq.com",
        alert_email_to=["admin@example.com"],
    )
    deps = WatchdogDependencies(
        service_is_active=lambda service: False,
        tcp_connect=lambda host, port: True,
        read_recent_logs=lambda cfg: "",
        send_email=lambda cfg, message: sent.append(message),
        read_replies=lambda cfg: [],
        run_refresh_command=lambda cfg: 0,
        now=lambda: 120.0,
        token_factory=lambda: "abc123",
        sleep=lambda seconds: None,
        log=lambda message: None,
        onebot_connected=lambda cfg: False,
    )

    report = run_watchdog(config, deps)

    assert report.status == "healthy"
    assert sent == []


def test_run_watchdog_uses_command_service_checks(tmp_path: Path) -> None:
    commands = []
    config = WatchdogConfig(
        state_path=str(tmp_path / "state.json"),
        service_check_mode="command",
        bot_check_command="check-bot",
        napcat_check_command="check-napcat",
        require_onebot_connection=False,
        smtp_user="sender@qq.com",
        smtp_password="smtp-code",
        alert_email_from="sender@qq.com",
        alert_email_to=["admin@example.com"],
    )
    deps = WatchdogDependencies(
        service_is_active=lambda service: False,
        tcp_connect=lambda host, port: True,
        read_recent_logs=lambda cfg: "",
        send_email=lambda cfg, message: None,
        read_replies=lambda cfg: [],
        run_refresh_command=lambda cfg: 0,
        run_check_command=lambda command: commands.append(command) or (1 if command == "check-bot" else 0),
        now=lambda: 120.0,
        token_factory=lambda: "abc123",
        sleep=lambda seconds: None,
        log=lambda message: None,
    )

    report = run_watchdog(config, deps)

    assert commands == ["check-bot", "check-napcat"]
    assert report.status == "unhealthy"
    assert "qq-rolebot.service is not active" in report.reasons


def test_run_watchdog_sends_recovery_after_unhealthy(tmp_path: Path) -> None:
    sent = []
    config = WatchdogConfig(
        state_path=str(tmp_path / "state.json"),
        smtp_user="sender@qq.com",
        smtp_password="smtp-code",
        alert_email_from="sender@qq.com",
        alert_email_to=["admin@example.com"],
    )
    unhealthy_deps = WatchdogDependencies(
        service_is_active=lambda service: False,
        tcp_connect=lambda host, port: False,
        read_recent_logs=lambda cfg: "",
        send_email=lambda cfg, message: sent.append(message),
        read_replies=lambda cfg: [],
        run_refresh_command=lambda cfg: 0,
        now=lambda: 100.0,
        token_factory=lambda: "abc123",
        sleep=lambda seconds: None,
        log=lambda message: None,
    )
    healthy_deps = WatchdogDependencies(
        service_is_active=lambda service: True,
        tcp_connect=lambda host, port: True,
        read_recent_logs=lambda cfg: "",
        send_email=lambda cfg, message: sent.append(message),
        read_replies=lambda cfg: [],
        run_refresh_command=lambda cfg: 0,
        now=lambda: 200.0,
        token_factory=lambda: "def456",
        sleep=lambda seconds: None,
        log=lambda message: None,
    )

    run_watchdog(config, unhealthy_deps)
    report = run_watchdog(config, healthy_deps)

    assert report.status == "healthy"
    assert [message["Subject"] for message in sent] == [
        "[napcat-watchdog] NapCat login may be offline [qr:abc123]",
        "[napcat-watchdog] NapCat login recovered",
    ]


def test_run_watchdog_rotates_click_token_for_new_offline_alert(tmp_path: Path) -> None:
    qr = tmp_path / "qrcode.png"
    qr.write_bytes(b"fake-png")
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"status":"healthy","active_qr_token":"old-token","active_qr_token_timestamp":10}',
        encoding="utf-8",
    )
    sent = []
    config = WatchdogConfig(
        state_path=str(state_path),
        qr_path=str(qr),
        click_public_base_url="https://bot.example.com",
        smtp_user="sender@qq.com",
        smtp_password="smtp-code",
        alert_email_from="sender@qq.com",
        alert_email_to=["admin@example.com"],
    )
    deps = WatchdogDependencies(
        service_is_active=lambda service: False,
        tcp_connect=lambda host, port: False,
        read_recent_logs=lambda cfg: "",
        send_email=lambda cfg, message: sent.append(message),
        read_replies=lambda cfg: [],
        run_refresh_command=lambda cfg: 0,
        now=lambda: 500.0,
        token_factory=lambda: "fresh-token",
        sleep=lambda seconds: None,
        log=lambda message: None,
    )

    run_watchdog(config, deps)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["active_qr_token"] == "fresh-token"
    assert state["active_qr_token_timestamp"] == 500
    assert "https://bot.example.com/watchdog/qr/fresh-token" in sent[0].as_string()
    assert "old-token" not in sent[0].as_string()


def test_run_watchdog_reply_sends_fresh_qr_and_marks_uid(tmp_path: Path) -> None:
    qr = tmp_path / "qrcode.png"
    qr.write_bytes(b"fake-png")
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"status":"unhealthy","active_qr_token":"abc123","handled_reply_uids":[]}',
        encoding="utf-8",
    )
    sent = []
    refreshes = []
    config = WatchdogConfig(
        state_path=str(state_path),
        qr_path=str(qr),
        reply_enabled=True,
        reply_allowed_senders=["admin@example.com"],
        smtp_user="sender@qq.com",
        smtp_password="smtp-code",
        alert_email_from="sender@qq.com",
        alert_email_to=["admin@example.com"],
        imap_user="sender@qq.com",
        imap_password="imap-code",
    )
    deps = WatchdogDependencies(
        service_is_active=lambda service: True,
        tcp_connect=lambda host, port: False,
        read_recent_logs=lambda cfg: "请扫描下面的二维码",
        send_email=lambda cfg, message: sent.append(message),
        read_replies=lambda cfg: [
            deps.reply_type(uid="42", sender="admin@example.com", subject="Re: [qr:abc123]", body="")
        ],
        run_refresh_command=lambda cfg: refreshes.append(cfg.qr_refresh_command) or 0,
        now=lambda: 120.0,
        token_factory=lambda: "abc123",
        sleep=lambda seconds: None,
        log=lambda message: None,
    )

    run_watchdog(config, deps)

    assert refreshes == ["systemctl restart napcat.service"]
    assert sent[0]["Subject"] == "[napcat-watchdog] Fresh NapCat login QR [qr:abc123]"
    assert '"42"' in state_path.read_text(encoding="utf-8")


def test_handle_qr_click_sends_fresh_qr_when_token_is_valid(tmp_path: Path) -> None:
    qr = tmp_path / "qrcode.png"
    qr.write_bytes(b"fake-png")
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"status":"unhealthy","active_qr_token":"abc123","active_qr_token_timestamp":100}',
        encoding="utf-8",
    )
    sent = []
    refreshes = []
    config = WatchdogConfig(
        state_path=str(state_path),
        qr_path=str(qr),
        smtp_user="sender@qq.com",
        smtp_password="smtp-code",
        alert_email_from="sender@qq.com",
        alert_email_to=["admin@example.com"],
    )
    deps = WatchdogDependencies(
        service_is_active=lambda service: True,
        tcp_connect=lambda host, port: True,
        read_recent_logs=lambda cfg: "",
        send_email=lambda cfg, message: sent.append(message),
        read_replies=lambda cfg: [],
        run_refresh_command=lambda cfg: refreshes.append(cfg.qr_refresh_command) or 0,
        now=lambda: 120.0,
        token_factory=lambda: "unused",
        sleep=lambda seconds: None,
        log=lambda message: None,
    )

    result = handle_qr_click(config, "abc123", deps)

    assert result == QrClickResult(status="sent", email_sent=True)
    assert refreshes == ["systemctl restart napcat.service"]
    assert len(sent) == 1
