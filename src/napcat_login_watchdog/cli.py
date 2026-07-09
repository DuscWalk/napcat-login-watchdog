from __future__ import annotations

import os
import sys

from napcat_login_watchdog.config import load_config
from napcat_login_watchdog.doctor import run_doctor
from napcat_login_watchdog.mail import build_email_message, email_configured
from napcat_login_watchdog.runner import default_dependencies, run_watchdog
from napcat_login_watchdog.webhook import serve_qr_click_webhook


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    config = load_config(os.environ)
    deps = default_dependencies()

    if argv in ([], ["run"]):
        report = run_watchdog(config, deps)
        print(f"status={report.status}")
        for reason in report.reasons:
            print(f"reason={reason}")
        return 0

    if argv == ["serve-click-webhook"]:
        serve_qr_click_webhook(config, deps)
        return 0

    if argv == ["doctor"]:
        for result in run_doctor(config, deps):
            name, status, detail = (
                (result.name, result.status, result.detail)
                if hasattr(result, "name")
                else result
            )
            print(f"[{status}] {name} - {detail}")
        return 0

    if argv == ["test-email"]:
        if not email_configured(config):
            print("alert email is not configured", file=sys.stderr)
            return 1
        deps.send_email(
            config,
            build_email_message(
                config,
                subject="[napcat-watchdog] Test email",
                body=(
                    "This is a test email from napcat-login-watchdog.\n\n"
                    "If you received it, SMTP delivery is working."
                ),
            ),
        )
        print("test email sent")
        return 0

    print(
        "usage: napcat-login-watchdog [run|doctor|test-email|serve-click-webhook]",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
