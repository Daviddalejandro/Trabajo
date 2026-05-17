"""Logging y observabilidad inicial (Fase 1)."""
from __future__ import annotations

import sys

from loguru import logger

from .config import settings


_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    settings.ensure_dirs()
    logger.remove()
    # En binarios PyInstaller --windowed sys.stderr puede ser None.
    if sys.stderr is not None:
        logger.add(
            sys.stderr,
            level=settings.log_level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level:<7}</level> | "
                "<cyan>{name}:{function}:{line}</cyan> | {message}"
            ),
            enqueue=False,
            backtrace=False,
            diagnose=False,
        )
    logger.add(
        settings.logs_dir / "bpmn_platform_{time:YYYY-MM-DD}.log",
        level=settings.log_level,
        rotation="00:00",
        retention=f"{settings.log_retention_days} days",
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )
    _configured = True
    logger.debug("Logging configurado en {}", settings.logs_dir)


def get_logger(name: str | None = None):
    if not _configured:
        configure_logging()
    return logger.bind(component=name) if name else logger
