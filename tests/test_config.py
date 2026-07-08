from napcat_login_watchdog.config import load_config


def test_load_config_uses_safe_defaults_and_mail_fallbacks() -> None:
    config = load_config(
        {
            "SMTP_USER": "sender@qq.com",
            "SMTP_PASSWORD": "smtp-code",
            "ALERT_EMAIL_TO": "admin@example.com,ops@example.com",
        }
    )

    assert config.bot_service == "qq-rolebot.service"
    assert config.napcat_service == "napcat.service"
    assert config.host == "127.0.0.1"
    assert config.port == 8080
    assert config.smtp_host == "smtp.qq.com"
    assert config.smtp_port == 465
    assert config.smtp_ssl is True
    assert config.alert_email_from == "sender@qq.com"
    assert config.alert_email_to == ["admin@example.com", "ops@example.com"]
    assert config.imap_user == "sender@qq.com"
    assert config.imap_password == "smtp-code"


def test_load_config_parses_onebot_http_and_click_settings() -> None:
    config = load_config(
        {
            "WATCHDOG_REQUIRE_ONEBOT_CONNECTION": "false",
            "WATCHDOG_REQUIRE_ONEBOT_HTTP_API": "true",
            "WATCHDOG_ONEBOT_HTTP_API_BASE": "http://127.0.0.1:3001/",
            "WATCHDOG_ONEBOT_HTTP_API_TOKEN": "api-token",
            "WATCHDOG_ONEBOT_HTTP_API_TIMEOUT_SECONDS": "7",
            "WATCHDOG_CLICK_PUBLIC_BASE_URL": "https://bot.example.com/base/",
            "WATCHDOG_CLICK_HOST": "0.0.0.0",
            "WATCHDOG_CLICK_PORT": "18081",
            "WATCHDOG_CLICK_PATH_PREFIX": "qr",
        }
    )

    assert config.require_onebot_connection is False
    assert config.require_onebot_http_api is True
    assert config.onebot_http_api_base == "http://127.0.0.1:3001"
    assert config.onebot_http_api_token == "api-token"
    assert config.onebot_http_api_timeout_seconds == 7
    assert config.click_public_base_url == "https://bot.example.com/base/"
    assert config.click_host == "0.0.0.0"
    assert config.click_port == 18081
    assert config.click_path_prefix == "/qr"
