"""Centralized logger configuration for the financial data platform."""

import logging
import os
from pathlib import Path

_loggers: dict = {}


def get_logger(name: str, log_dir: str = "logs") -> logging.Logger:
    """Return a configured logger. Cached per-name to avoid duplicate handlers."""
    if name in _loggers:
        return _loggers[name]

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        _loggers[name] = logger
        return logger

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(os.path.join(log_dir, "platform.log"))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    _loggers[name] = logger
    return logger
