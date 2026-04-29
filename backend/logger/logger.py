from __future__ import annotations

import logging
import sys

from loguru import logger as _loguru


class InterceptHandler(logging.Handler):
    """将标准 logging 重定向到 loguru"""

    def emit(self, record: logging.LogRecord) -> None:
        level = _loguru.level(record.levelname).name if record.levelname in _loguru._core.levels else record.levelno
        _loguru.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(level: str = "INFO") -> None:
    _loguru.remove()
    _loguru.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <7}</level> | <cyan>{name}</cyan> | {message}",
        level=level,
        colorize=True,
    )
    _loguru.add(
        "data/logs/degenclaw-{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name} | {message}",
        level=level,
        rotation="1 day",
        retention="7 days",
        compression="gz",
    )

    logging.basicConfig(handlers=[InterceptHandler()], level=logging.getLevelName(level), force=True)
