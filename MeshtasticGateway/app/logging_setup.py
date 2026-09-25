"""Rotating file logging. Never logs passwords or credentials."""

from __future__ import annotations

import logging
import logging.handlers
import re
from typing import Iterable

from app.config import settings

SECRET_KEYS = ("password", "passwd", "secret", "token", "credential", "mqtt_password")
_KV_RE = re.compile(
    r"(?i)\b(" + "|".join(SECRET_KEYS) + r")\b(\s*[=:]\s*)([^\s,;]+)"
)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = _KV_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", message)
        if record.args:
            record.args = tuple(_redact_value(a) for a in record.args) if isinstance(record.args, tuple) else record.args
        record.msg = redacted
        record.args = ()
        return True


def _redact_value(value):
    if isinstance(value, dict):
        return {
            k: ("***" if any(s in str(k).lower() for s in SECRET_KEYS) else _redact_value(v))
            for k, v in value.items()
        }
    if isinstance(value, str):
        return _KV_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", value)
    return value


def setup_logging() -> logging.Logger:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("meshtastic_gateway")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.handlers.RotatingFileHandler(
        settings.log_file,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactingFilter())
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(RedactingFilter())
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    logger = logging.getLogger("meshtastic_gateway")
    if not logger.handlers:
        return setup_logging()
    return logger


def tail_log(lines: int = 200) -> list[str]:
    path = settings.log_file
    if not path.exists():
        return []
    data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return data[-max(1, min(lines, 2000)) :]


def iter_redacted(items: Iterable[str]) -> list[str]:
    return [_KV_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", line) for line in items]
