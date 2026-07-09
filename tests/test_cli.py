from napcat_login_watchdog.cli import main


def test_cli_rejects_unknown_arguments() -> None:
    assert main(["--unknown"]) == 2


def test_cli_accepts_doctor_argument(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "napcat_login_watchdog.cli.run_doctor",
        lambda config, deps: [("SMTP", "ok", "login succeeded")],
    )

    assert main(["doctor"]) == 0

    assert "[ok] SMTP - login succeeded" in capsys.readouterr().out
