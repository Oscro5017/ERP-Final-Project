import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Settings, get_settings

_MANAGED_HANDLER_ATTRIBUTE = "_erp_managed_handler"
_ROOT_SIGNATURE_ATTRIBUTE = "_erp_logging_signature"


def configure_logging(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    log_level = getattr(logging, settings.log_level.strip().upper(), logging.INFO)
    log_dir = Path(settings.log_dir).expanduser()
    signature = (log_level, str(log_dir.resolve()))
    root_logger = logging.getLogger()

    if getattr(root_logger, _ROOT_SIGNATURE_ATTRIBUTE, None) == signature:
        return

    for handler in root_logger.handlers[:]:
        if getattr(handler, _MANAGED_HANDLER_ATTRIBUTE, False):
            root_logger.removeHandler(handler)
            handler.close()

    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    setattr(console_handler, _MANAGED_HANDLER_ATTRIBUTE, True)

    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    setattr(file_handler, _MANAGED_HANDLER_ATTRIBUTE, True)

    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    setattr(root_logger, _ROOT_SIGNATURE_ATTRIBUTE, signature)
