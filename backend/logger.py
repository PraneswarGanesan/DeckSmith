import logging
import sys
from datetime import datetime
import os

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)  
    logger.propagate = False        

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    # File logging only (avoid Windows terminal Unicode issues)
    log_filename = datetime.now().strftime("%Y-%m-%d") + ".log"
    file_handler = logging.FileHandler(
        os.path.join(LOG_DIR, log_filename), 
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    return logger