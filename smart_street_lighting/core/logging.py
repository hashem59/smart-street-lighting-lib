"""
Project-wide logging configuration (S4-04 / item 12).

Central place to configure the root logger so every module emits at
consistent levels and formats. CLI entry points (uc01_park_pathway.py)
keep using ``print()`` for the human-facing report; non-entry-point
modules switch to ``logging.getLogger(__name__)``.

Usage::

    from smart_street_lighting.core.logging import get_logger
    log = get_logger(__name__)
    log.info("loaded %d sensors", n)

Env override:
    SSL_LOG_LEVEL=DEBUG | INFO | WARNING | ERROR     (default: INFO)
    SSL_LOG_FILE=/path/to/file.log                    (default: stderr only)
"""

import logging
import os
import sys
from typing import Optional


_CONFIGURED = False
_DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%dT%H:%M:%S"


def configure(
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    format_string: Optional[str] = None,
) -> None:
    """Configure the root logger. Idempotent.

    Reads ``SSL_LOG_LEVEL`` and ``SSL_LOG_FILE`` env vars if the args are
    None. Adds a stderr handler unconditionally; adds a file handler if
    ``log_file`` is supplied.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    lvl_name = (level or os.environ.get("SSL_LOG_LEVEL", "INFO")).upper()
    lvl = getattr(logging, lvl_name, logging.INFO)
    fmt = format_string or _DEFAULT_FORMAT

    root = logging.getLogger()
    root.setLevel(lvl)

    # Remove default handlers that pytest / Jupyter sometimes leave behind
    # so we don't end up with duplicated lines.
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt, datefmt=_DEFAULT_DATEFMT))
    root.addHandler(handler)

    file_target = log_file or os.environ.get("SSL_LOG_FILE")
    if file_target:
        fh = logging.FileHandler(file_target, encoding="utf-8")
        fh.setFormatter(logging.Formatter(fmt, datefmt=_DEFAULT_DATEFMT))
        root.addHandler(fh)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger, ensuring the root is configured."""
    if not _CONFIGURED:
        configure()
    return logging.getLogger(name)
