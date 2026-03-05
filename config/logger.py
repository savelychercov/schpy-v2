"""
Конфигурация системы логирования для учебного расписания.

Модуль предоставляет централизованную систему логирования с разными уровнями:
- DEBUG: Детальная информация для отладки
- INFO: Общая информация о работе программы
- WARNING: Предупреждения о потенциальных проблемах
- ERROR: Ошибки, которые не приводят к остановке программы
- CRITICAL: Критические ошибки, приводящие к остановке

Использует ротацию логов для управления размером файлов.
"""

import contextlib
import locale
import logging
import logging.handlers
from pathlib import Path

# Устанавливаем локаль для правильной работы с кириллицей
try:
    locale.setlocale(locale.LC_ALL, "Russian_Russia.1251")
except (locale.Error, OSError):
    with contextlib.suppress(BaseException):
        locale.setlocale(locale.LC_ALL, "ru_RU.UTF-8")

from .settings import LOG_LEVELS


def setup_logger(name: str = "schpy", log_level: str = None) -> logging.Logger:
    """
    Настройка логгера с ротацией файлов и консольным выводом.

    Args:
        name: Имя логгера
        log_level: Уровень логирования (если None, используется из настроек)

    Returns:
        Настроенный логгер
    """
    # Создаем директорию для логов
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # Определяем уровень логирования
    if log_level is None:
        log_level = LOG_LEVELS.get("default", "INFO")

    # Настройка формата логов
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Создаем логгер
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))

    # Очищаем существующие обработчики
    logger.handlers.clear()

    # Обработчик для файла с ротацией (макс. 10MB, хранить 5 файлов)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / f"{name}.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8-sig",  # Используем UTF-8 с BOM для лучшей совместимости
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Обработчик для ошибок в отдельный файл
    error_handler = logging.handlers.RotatingFileHandler(
        log_dir / f"{name}_errors.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8-sig",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    # Консольный обработчик (только для INFO и выше)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s: %(message)s", datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger


# Глобальный логгер для всего проекта
logger = setup_logger("schpy")


def get_logger(name: str = None) -> logging.Logger:
    """
    Получить логгер для конкретного модуля.

    Args:
        name: Имя модуля (если None, возвращает основной логгер)

    Returns:
        Логгер для модуля
    """
    if name is None:
        return logger

    # Получаем уровень для конкретного модуля
    module_level = LOG_LEVELS.get(name, LOG_LEVELS.get("default", "INFO"))

    # Создаем логгер для модуля
    logger_name = f"schpy.{name}"
    module_logger = logging.getLogger(logger_name)

    # Если логгер еще не настроен, настраиваем его
    if not module_logger.handlers:
        module_logger = setup_logger(logger_name, module_level)
        # Устанавливаем propagate=False чтобы избежать дублирования
        module_logger.propagate = False

    return module_logger
