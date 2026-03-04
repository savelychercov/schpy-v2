"""
Константы и перечисления для приложения SchPy.
"""

from datetime import time
from enum import Enum


class PairType(str, Enum):
    """Типы учебных пар."""

    OFFLINE = "Офлайн"
    ONLINE = "Онлайн"


class DayOfWeek(str, Enum):
    """Дни недели."""

    MONDAY = "Понедельник"
    TUESDAY = "Вторник"
    WEDNESDAY = "Среда"
    THURSDAY = "Четверг"
    FRIDAY = "Пятница"
    SATURDAY = "Суббота"
    SUNDAY = "Воскресенье"


class RoomPrefix(str, Enum):
    """Префиксы аудиторий."""

    CLASSROOM = "К"  # Классная комната (офлайн)
    DIGITAL = "Д"  # Цифровая аудитория (онлайн)


# Константы
PAIRS_PER_DAY = 6
MAX_PAIR_NUMBER = 6
MIN_PAIR_NUMBER = 1

# Настройки генерации расписания
DEFAULT_ITERATIONS = 10000
MIN_ITERATIONS = 1000
MAX_ITERATIONS = 500000

# Рабочие часы преподавателей
MAX_WORKING_HOURS_FOR_TEACHER = 36

# Модификаторы рейтинга
UNISSUED_HOURS_RATING_MODIFIER = 3
TEACHERS_GAPS_RATING_MODIFIER = 5
OFFLINE_PAIRS_GAPS_RATING_MODIFIER = 13
OVERWORKED_TEACHERS_RATING_MODIFIER = 50

# Настройки UI
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 600
WINDOW_X = 100
WINDOW_Y = 100
HELP_LABEL_WIDTH = 265

# Настройки времени для расписания
TEACHERS_SCHEDULE_TIME = {
    1: (time(8, 0), time(9, 30)),  # first pair for 1 shift, online for 2 shift
    2: (time(9, 40), time(11, 10)),  # second pair for 1 shift
    3: (time(11, 30), time(13, 0)),  # first pair for 2 shift, online for 3 shift
    4: (time(13, 10), time(14, 40)),  # second pair for 2 shift
    5: (time(15, 0), time(16, 30)),  # first pair for 3 shift
    6: (time(16, 40), time(18, 10)),  # second pair for 3 shift, online for 1 shift
}

# Дни недели (кортежи для обратной совместимости)
DAYS = (
    DayOfWeek.MONDAY.value,
    DayOfWeek.TUESDAY.value,
    DayOfWeek.WEDNESDAY.value,
    DayOfWeek.THURSDAY.value,
    DayOfWeek.FRIDAY.value,
    DayOfWeek.SATURDAY.value,
    DayOfWeek.SUNDAY.value,
)

WORKWEEK_DAYS = (
    DayOfWeek.MONDAY.value,
    DayOfWeek.TUESDAY.value,
    DayOfWeek.WEDNESDAY.value,
    DayOfWeek.THURSDAY.value,
    DayOfWeek.FRIDAY.value,
)

# Настройки базы данных
DB_FILE = "db.pickle"
DB_PATH_NAME = "SchPyPickleData"

# Настройки Excel
EXCEL_COLUMN_WIDTH_PADDING = 2
