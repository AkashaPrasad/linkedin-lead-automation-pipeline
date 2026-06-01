import logging
import sys
from pathlib import Path

LOG_FILE = Path(__file__).parent.parent / "pipeline.log"

_fmt = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

def _make_handler(stream) -> logging.StreamHandler:
    h = logging.StreamHandler(stream)
    h.setFormatter(_fmt)
    return h

def get_logger(name: str = "pipeline") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(_make_handler(sys.stdout))
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(_fmt)
        logger.addHandler(file_handler)
        logger.propagate = False
    return logger
