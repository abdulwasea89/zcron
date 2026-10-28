"""Compact, readable development console logs with useful source locations."""

from __future__ import annotations

import logging
import sys
import traceback


class ConsoleFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[2m",
        logging.INFO: "\033[36m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[1;37;41m",
    }
    RESET = "\033[0m"

    def __init__(self, *, color: bool) -> None:
        super().__init__()
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        level = record.levelname
        location = f"{record.pathname}:{record.lineno}"
        timestamp = self.formatTime(record, "%H:%M:%S")
        message = record.getMessage()
        color = self.COLORS.get(record.levelno, "") if self.color else ""
        reset = self.RESET if color else ""
        lines = [
            f"{color}╭─ {timestamp}  {level:<8} {record.name}{reset}",
            f"{color}│{reset} {location}",
            f"{color}│{reset} {message}",
        ]
        if record.exc_info:
            lines.append(f"{color}├─ traceback{reset}")
            rendered = traceback.format_exception(*record.exc_info)
            lines.extend(
                f"{color}│{reset} {line.rstrip()}"
                for part in rendered
                for line in part.splitlines()
            )
        lines.append(f"{color}╰{'─' * 72}{reset}")
        return "\n".join(lines)


def configure_console_logging() -> None:
    """Route application and Uvicorn logs through one source-aware formatter."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(ConsoleFormatter(color=sys.stderr.isatty()))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    # Uvicorn installs non-propagating handlers before importing the app.
    # Let its server/access records use the same formatting as application errors.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
