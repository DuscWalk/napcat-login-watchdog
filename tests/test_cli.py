from napcat_login_watchdog.cli import main


def test_cli_rejects_unknown_arguments() -> None:
    assert main(["--unknown"]) == 2
