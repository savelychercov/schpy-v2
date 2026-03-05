"""
Настройки проекта и конфигурация логирования.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Базовые настройки проекта
BASE_DIR = Path(__file__).parent.parent
LOGS_DIR = BASE_DIR / "logs"

# Настройки логирования
LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "console": {"format": "%(levelname)s: %(message)s"},
    },
    "handlers": {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "standard",
            "filename": str(LOGS_DIR / "schpy.log"),
            "maxBytes": 10 * 1024 * 1024,  # 10MB
            "backupCount": 5,
            "encoding": "utf-8",
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "ERROR",
            "formatter": "standard",
            "filename": str(LOGS_DIR / "schpy_errors.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 3,
            "encoding": "utf-8",
        },
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "console",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "schpy": {
            "handlers": ["file", "error_file", "console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "schpy.db": {
            "handlers": ["file", "error_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "schpy.window": {
            "handlers": ["file", "error_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "schpy.schedule_maker": {
            "handlers": ["file", "error_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "schpy.best_of": {
            "handlers": ["file", "error_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "schpy.main": {
            "handlers": ["file", "error_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}

# Уровни логирования для разных модулей (можно переопределить через переменные окружения)
LOG_LEVELS = {
    "default": os.getenv("SCHPY_LOG_LEVEL", "INFO"),
    "db": os.getenv("SCHPY_DB_LOG_LEVEL", "INFO"),
    "window": os.getenv("SCHPY_WINDOW_LOG_LEVEL", "INFO"),
    "schedule_maker": os.getenv("SCHPY_SCHEDULE_MAKER_LOG_LEVEL", "INFO"),
    "best_of": os.getenv("SCHPY_BEST_OF_LOG_LEVEL", "INFO"),
    "main": os.getenv("SCHPY_MAIN_LOG_LEVEL", "INFO"),
}

# Настройки производительности
ENABLE_DEBUG_LOGS = os.getenv("SCHPY_DEBUG", "false").lower() == "true"
ENABLE_PERFORMANCE_LOGS = os.getenv("SCHPY_PERFORMANCE_LOGS", "false").lower() == "true"
ENABLE_SCHEDULE_LOGS = os.getenv("SCHPY_SCHEDULE_LOGS", "false").lower() == "true"
