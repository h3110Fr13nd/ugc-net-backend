import logging
import logging.handlers
import os
import sys
import uuid
from contextvars import ContextVar

# Public contextvar used by middleware to set the current request id
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    """Injects the request_id from the contextvar into the log record."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


class ColorLevelFormatter(logging.Formatter):
    RESET = "\033[0m"
    COLORS = {
        logging.DEBUG: "\033[94m",
        logging.INFO: "\033[92m",
        logging.WARNING: "\033[93m",
        logging.ERROR: "\033[91m",
        logging.CRITICAL: "\033[95m",
    }
    PATH_COLOR = "\033[96m"
    FUNC_COLOR = "\033[93m"
    LINE_COLOR = "\033[95m"
    MODULE_COLOR = "\033[91m"

    def __init__(self, fmt=None, datefmt=None, style='%', validate=True, *, defaults=None, colorize=False):
        super().__init__(fmt, datefmt, style, validate=validate, defaults=defaults)
        self.colorize = colorize

    def format(self, record: logging.LogRecord) -> str:
        try:
            record.relativepath = os.path.relpath(record.pathname, start=os.getcwd())
        except Exception:
            record.relativepath = record.pathname
        level_color = self.COLORS.get(record.levelno, self.RESET)
        if self.colorize:
            record.levelname = f"{level_color}{record.levelname}{self.RESET}"
            record.pathname = f"{self.PATH_COLOR}{record.relativepath}{self.RESET}"
            record.relativepath = f"{self.PATH_COLOR}{record.relativepath}{self.RESET}"
            record.funcName = f"{self.FUNC_COLOR}{record.funcName}{self.RESET}"
            record.lineno = f"{self.LINE_COLOR}{record.lineno}{self.RESET}"
            record.module = f"{self.MODULE_COLOR}{record.module}{self.RESET}"
        return super().format(record)


class RelativePathFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        try:
            record.relativepath = os.path.relpath(record.pathname, start=os.getcwd())
        except Exception:
            record.relativepath = record.pathname
        return super().format(record)


def get_logger(
    name: str = __name__,
    log_dir: str = "logs",
    log_file: str = "app.log",
    level: int = None,
    stream: bool = True,
) -> logging.Logger:
    """Configure and return a logger that injects request IDs from contextvar.

    - Adds a timed rotating file handler (midnight, 7 backups)
    - Adds a console handler with optional color
    - Attaches a RequestIdFilter to handlers so `%(request_id)s` is available
    """
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger

    logger.setLevel(level or os.getenv("LOG_LEVEL", logging.DEBUG))

    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_file)

    request_filter = RequestIdFilter()

    # File handler
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_path, when="midnight", interval=1, backupCount=7, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = RelativePathFormatter(
        "%(asctime)s  %(levelname)-6s [%(request_id)s] {%(relativepath)s:%(lineno)s} (%(funcName)s) %(message)s",
        datefmt="%d-%m-%Y %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(request_filter)
    logger.addHandler(file_handler)

    # Console handler
    if stream:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = ColorLevelFormatter(
            "%(levelname)-6s [%(request_id)s] {%(relativepath)s:%(lineno)s} (%(funcName)s) %(message)s",
            colorize=os.getenv("COLOR_LOGGING", "true").lower() == "true",
        )
        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(request_filter)
        logger.addHandler(console_handler)

    logger.propagate = False

    return logger
