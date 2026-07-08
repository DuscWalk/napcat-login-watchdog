from __future__ import annotations

import os
import sys

from napcat_login_watchdog.config import load_config
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

    print("usage: napcat-login-watchdog [run|serve-click-webhook]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
