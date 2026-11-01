"""Shared utility functions for the financial analytics system."""

import logging
import os
from pathlib import Path


def setup_logger(name: str, log_dir: str = "logs") -> logging.Logger:
    """Configure and return a named logger with file + console handlers."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")

    # File handler
    fh = logging.FileHandler(os.path.join(log_dir, "analytics.log"))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def safe_div(numerator, denominator, default=None):
    """Division that returns default instead of raising ZeroDivisionError."""
    try:
        if denominator == 0 or denominator is None:
            return default
        return numerator / denominator
    except (TypeError, ZeroDivisionError):
        return default


def cagr(start_val, end_val, periods: int):
    """Compound Annual Growth Rate. Returns None on invalid inputs."""
    try:
        if start_val is None or end_val is None or periods <= 0 or start_val == 0:
            return None
        if start_val < 0 or end_val < 0:
            return None  # CAGR undefined for negatives
        return (end_val / start_val) ** (1 / periods) - 1
    except (TypeError, ZeroDivisionError, ValueError):
        return None


def yoy_growth(current, previous):
    """Year-over-year growth rate."""
    try:
        if previous is None or previous == 0 or current is None:
            return None
        return (current - previous) / abs(previous)
    except (TypeError, ZeroDivisionError):
        return None
