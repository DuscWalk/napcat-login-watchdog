from napcat_login_watchdog.config import WatchdogConfig
from napcat_login_watchdog.doctor import DiagnosticResult, run_doctor
from napcat_login_watchdog.runner import WatchdogDependencies


def test_run_doctor_reports_core_checks_without_sending_mail() -> None:
    sent = []
    config = WatchdogConfig(
        require_onebot_http_api=True,
        onebot_http_api_base="http://127.0.0.1:3001",
        smtp_user="sender@qq.com",
        smtp_password="smtp-code",
        alert_email_from="sender@qq.com",
        alert_email_to=["admin@example.com"],
    )
    deps = WatchdogDependencies(
        service_is_active=lambda service: service == "napcat.service",
        tcp_connect=lambda host, port: False,
        read_recent_logs=lambda cfg: "",
        send_email=lambda cfg, message: sent.append(message),
        read_replies=lambda cfg: [],
        run_refresh_command=lambda cfg: 0,
        now=lambda: 100.0,
        token_factory=lambda: "abc123",
        sleep=lambda seconds: None,
        log=lambda message: None,
        onebot_connected=lambda cfg: True,
        onebot_http_api_healthy=lambda cfg: False,
        smtp_login_ok=lambda cfg: True,
        imap_login_ok=lambda cfg: True,
    )

    results = run_doctor(config, deps)

    assert DiagnosticResult("bot service", "fail", "qq-rolebot.service is not healthy") in results
    assert DiagnosticResult("napcat service", "ok", "napcat.service is healthy") in results
    assert DiagnosticResult("tcp port", "fail", "127.0.0.1:8080 is not reachable") in results
    assert DiagnosticResult("OneBot HTTP API", "fail", "status check failed") in results
    assert DiagnosticResult("SMTP", "ok", "login succeeded") in results
    assert sent == []
