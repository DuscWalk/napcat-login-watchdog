from __future__ import annotations

import glob
from pathlib import Path
from urllib.parse import unquote, urlsplit

from napcat_login_watchdog.config import WatchdogConfig, normalize_path_prefix


def fresh_qr(path: Path, *, now: float, max_age_seconds: int) -> Path | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    if not path.is_file() or stat.st_size <= 0:
        return None
    if now - stat.st_mtime > max_age_seconds:
        return None
    return path


def find_fresh_qr(config: WatchdogConfig, *, now: float) -> Path | None:
    if config.qr_path:
        explicit = fresh_qr(Path(config.qr_path), now=now, max_age_seconds=config.qr_max_age_seconds)
        if explicit is not None:
            return explicit
    candidates = [
        Path(path)
        for path in glob.glob(config.qr_glob, recursive=True)
        if fresh_qr(Path(path), now=now, max_age_seconds=config.qr_max_age_seconds) is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def qr_click_token_from_path(config: WatchdogConfig, request_target: str) -> str:
    path = urlsplit(request_target).path
    prefix = normalize_path_prefix(config.click_path_prefix)
    token_prefix = f"{prefix}/"
    if not path.startswith(token_prefix):
        return ""
    token = unquote(path[len(token_prefix) :])
    if not token or "/" in token:
        return ""
    return token
