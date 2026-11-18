"""JSON logs: one object per line with the request id; ids, never content.

Legal D-7: records carry ids, counts, classes and route templates, never message
bodies, passwords, tokens, e-mail addresses or raw URLs. Two guards back the rule
up (D-6). An exception keeps its class and stack frames but loses its text,
because driver errors repeat SQL parameters. Every secret the process knows
(SECRET_KEY, FERNET_KEY, the database password, the seed passwords) is replaced
by [redacted] before a line is written.
"""

import json
import logging
import traceback
from collections.abc import Iterable
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Set by the request middleware (app/api/middleware.py) for each HTTP request.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

REDACTED = "[redacted]"
# Shorter values are not worth redacting and would mangle ordinary words.
MIN_REDACTED_LENGTH = 8
# Attributes every LogRecord has; anything else arrived through extra=.
_STANDARD_ATTRIBUTES = frozenset(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "request_id",
}
# Uvicorn's own handlers are replaced: its records go through the root handler.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")
# Libraries that log SQL parameters, outbound URLs or form fields at info or
# debug level. They stay at warning whatever LOG_LEVEL says.
_QUIET_LOGGERS = ("sqlalchemy", "httpx", "httpcore", "multipart", "python_multipart")


class JsonFormatter(logging.Formatter):
    """Formats a record as one JSON object and redacts the known secrets."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        values = {value for value in secrets if len(value) >= MIN_REDACTED_LENGTH}
        # The JSON-escaped form too, in case a secret holds a quote or backslash.
        values |= {json.dumps(value)[1:-1] for value in values}
        self._secrets = sorted(values, key=len, reverse=True)

    def format(self, record: logging.LogRecord) -> str:
        at = datetime.fromtimestamp(record.created, UTC)
        entry: dict[str, Any] = {
            "at": at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or request_id_var.get()
        if request_id:
            entry["request_id"] = request_id
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRIBUTES:
                entry[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            # The class and the frames; the exception text may carry content.
            entry["error"] = record.exc_info[0].__name__
            entry["stack"] = "".join(traceback.format_tb(record.exc_info[2]))
        line = json.dumps(entry, default=str, ensure_ascii=False)
        for secret in self._secrets:
            line = line.replace(secret, REDACTED)
        return line


def quiet_libraries() -> None:
    """Keep the libraries that would log content at warning level."""
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def configure_logging(level: str, secrets: Iterable[str] = ()) -> None:
    """Send every log record, uvicorn's included, as JSON to standard error."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(secrets))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for name in _UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    quiet_libraries()
