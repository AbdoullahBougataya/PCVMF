import logging
import sys
from typing import Optional


class FlushStreamHandler(logging.StreamHandler):
    """StreamHandler that flushes after every log message for real-time multiprocessing output."""
    def emit(self, record):
        super().emit(record)
        self.flush()


def setup_logger(name: str, level: str = "INFO", log_file: Optional[str] = None, force_reinit: bool = False) -> logging.Logger:
    """Configures and returns a process-aware logger.

    Args:
        name: Name tag for the logger (e.g., "CV-Pipeline", "Main-Task").
        level: Logging level string ("DEBUG", "INFO", "WARNING", "ERROR").
        log_file: Optional file path to write log outputs.
        force_reinit: Force handler re-creation (useful after multiprocessing spawn).

    Returns:
        Configured logging instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    if force_reinit:
        logger.handlers.clear()
    elif logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%H:%M:%S"
    )

    console_handler = FlushStreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
