from napcat_login_watchdog.cli import main
from napcat_login_watchdog.config import WatchdogConfig
from napcat_login_watchdog.runner import WatchdogDependencies


def test_cli_rejects_unknown_arguments() -> None:
    assert main(["--unknown"]) == 2


def test_cli_accepts_doctor_argument(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "napcat_login_watchdog.cli.run_doctor",
        lambda config, deps: [("SMTP", "ok", "login succeeded")],
    )

    assert main(["doctor"]) == 0

    assert "[ok] SMTP - login succeeded" in capsys.readouterr().out


def test_cli_test_email_sends_configured_message(monkeypatch, capsys) -> None:
    sent = []
    config = WatchdogConfig(
        smtp_user="sender@example.com",
        smtp_password="secret",
        alert_email_from="sender@example.com",
        alert_email_to=["admin@example.com"],
    )
    deps = WatchdogDependencies(
        service_is_active=lambda service: True,
        tcp_connect=lambda host, port: True,
        read_recent_logs=lambda cfg: "",
        send_email=lambda cfg, message: sent.append(message),
        read_replies=lambda cfg: [],
        run_refresh_command=lambda cfg: 0,
        now=lambda: 100.0,
        token_factory=lambda: "abc123",
        sleep=lambda seconds: None,
        log=lambda message: None,
    )
    monkeypatch.setattr("napcat_login_watchdog.cli.load_config", lambda env: config)
    monkeypatch.setattr("napcat_login_watchdog.cli.default_dependencies", lambda: deps)

    assert main(["test-email"]) == 0

    assert len(sent) == 1
    assert sent[0]["Subject"] == "[napcat-watchdog] Test email"
    assert "sent" in capsys.readouterr().out


def test_cli_test_email_reports_missing_configuration(monkeypatch, capsys) -> None:
    monkeypatch.setattr("napcat_login_watchdog.cli.load_config", lambda env: WatchdogConfig())

    assert main(["test-email"]) == 1

    assert "not configured" in capsys.readouterr().err
