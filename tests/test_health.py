from napcat_login_watchdog.config import WatchdogConfig
from napcat_login_watchdog.health import (
    HealthReport,
    decide_status_email,
    evaluate_health,
    onebot_connection_from_ss,
    onebot_http_api_healthy_from_payloads,
)


def test_evaluate_health_reports_failed_signals() -> None:
    report = evaluate_health(
        WatchdogConfig(),
        bot_active=False,
        napcat_active=True,
        tcp_ok=False,
        onebot_connected=False,
        onebot_http_api_healthy=True,
        recent_logs="请扫描下面的二维码",
    )

    assert report.status == "unhealthy"
    assert "qq-rolebot.service is not active" in report.reasons
    assert "127.0.0.1:8080 is not reachable" in report.reasons
    assert "OneBot reverse WebSocket is not connected" in report.reasons
    assert "NapCat login requires QR/manual verification" in report.reasons


def test_evaluate_health_requires_onebot_http_when_enabled() -> None:
    config = WatchdogConfig(require_onebot_http_api=True)

    report = evaluate_health(
        config,
        bot_active=True,
        napcat_active=True,
        tcp_ok=True,
        onebot_connected=True,
        onebot_http_api_healthy=False,
        recent_logs="",
    )

    assert report == HealthReport(
        status="unhealthy",
        reasons=["OneBot HTTP API status check failed"],
    )


def test_evaluate_health_ignores_stale_offline_logs_after_new_message() -> None:
    logs = "\n".join(
        [
            "Jul 10 14:58:33 host app: [notice.bot_offline]: login expired",
            "Jul 10 15:12:07 host app: OneBot V11 | Bot 3961601898 connected",
            "Jul 10 15:12:15 host app: [message.private.friend]: Message 1 from 1 '你好'",
        ]
    )

    report = evaluate_health(
        WatchdogConfig(),
        bot_active=True,
        napcat_active=True,
        tcp_ok=True,
        onebot_connected=True,
        onebot_http_api_healthy=True,
        recent_logs=logs,
    )

    assert report == HealthReport(status="healthy", reasons=[])


def test_evaluate_health_keeps_newer_offline_logs_unhealthy() -> None:
    logs = "\n".join(
        [
            "Jul 10 15:12:15 host app: [message.private.friend]: Message 1 from 1 '你好'",
            "Jul 10 15:13:33 host app: [notice.bot_offline]: login expired",
        ]
    )

    report = evaluate_health(
        WatchdogConfig(),
        bot_active=True,
        napcat_active=True,
        tcp_ok=True,
        onebot_connected=True,
        onebot_http_api_healthy=True,
        recent_logs=logs,
    )

    assert report.status == "unhealthy"
    assert "NapCat offline/login-expired marker found" in report.reasons


def test_onebot_connection_from_ss_detects_established_local_connection() -> None:
    output = "ESTAB 0 0 127.0.0.1:41980 127.0.0.1:8080 users:((\"qq\",pid=1,fd=1))\n"

    assert onebot_connection_from_ss(output, "127.0.0.1", 8080) is True
    assert onebot_connection_from_ss(output, "127.0.0.1", 3001) is False


def test_onebot_http_payload_health_requires_zero_retcodes_and_online_not_false() -> None:
    assert (
        onebot_http_api_healthy_from_payloads(
            {"retcode": 0, "data": {"user_id": 123}},
            {"retcode": 0, "data": {"online": True}},
        )
        is True
    )
    assert (
        onebot_http_api_healthy_from_payloads(
            {"retcode": 0, "data": {"user_id": 123}},
            {"retcode": 0, "data": {"online": False}},
        )
        is False
    )
    assert (
        onebot_http_api_healthy_from_payloads(
            {"retcode": 1404},
            {"retcode": 0, "data": {"online": True}},
        )
        is False
    )


def test_decide_status_email_only_on_transitions() -> None:
    unhealthy = HealthReport("unhealthy", ["offline"])
    healthy = HealthReport("healthy", [])

    assert decide_status_email({}, unhealthy, send_recovery=True) == "offline"
    assert decide_status_email({"status": "healthy"}, unhealthy, send_recovery=True) == "offline"
    assert decide_status_email({"status": "unhealthy"}, unhealthy, send_recovery=True) is None
    assert decide_status_email({"status": "unhealthy"}, healthy, send_recovery=True) == "recovery"
    assert decide_status_email({"status": "unhealthy"}, healthy, send_recovery=False) is None


def test_decide_status_email_repeats_offline_after_cooldown() -> None:
    unhealthy = HealthReport("unhealthy", ["offline"])

    assert (
        decide_status_email(
            {"status": "unhealthy", "last_alert_timestamp": 100},
            unhealthy,
            send_recovery=True,
            now=500,
            repeat_seconds=300,
        )
        == "offline"
    )
    assert (
        decide_status_email(
            {"status": "unhealthy", "last_alert_timestamp": 100},
            unhealthy,
            send_recovery=True,
            now=200,
            repeat_seconds=300,
        )
        is None
    )
