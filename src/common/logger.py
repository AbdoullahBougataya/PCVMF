import logging
import sys


def setup_logger(name: str = "Framework", level: str = "INFO") -> logging.Logger:
    """Configures and returns a process-aware logger instance."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="[%(asctime)s.%(msecs)03d] [%(levelname)s] [%(processName)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger
