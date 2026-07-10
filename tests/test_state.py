import os
from pathlib import Path

from napcat_login_watchdog.state import save_state


def test_save_state_writes_private_permissions(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    original_umask = os.umask(0o022)
    try:
        save_state(state_path, {"active_qr_token": "token"})
    finally:
        os.umask(original_umask)

    assert state_path.stat().st_mode & 0o777 == 0o600
