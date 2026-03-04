"""
Pydantic схемы для структурирования данных учебного расписания.

Модуль определяет строгие типизированные модели для всех сущностей системы:
- Временные интервалы и пары
- Преподаватели и их расписания
- Аудитории и доступность
- Учебные группы и дисциплины
- Полный контейнер данных

Использует Pydantic для валидации, сериализации и документации данных.
Предназначен для замены свободных классов из db.py на строгие схемы.
"""

from datetime import time

from pydantic import BaseModel, field_validator


class PairTimeSchema(BaseModel):
    """Временной интервал учебной пары с типом (онлайн/офлайн)"""

    start: time
    end: time
    pair_type: str

    @field_validator("end")
    @classmethod
    def validate_end_time(cls, v, info):
        if "start" in info.data and v <= info.data["start"]:
            msg = "Время окончания должно быть позже времени начала"
            raise ValueError(msg)
        return v

    def get_str(self) -> str:
        """Строковое представление времени"""
        return (
            f"{str(self.start.hour).rjust(2, '0')}:{str(self.start.minute).rjust(2, '0')} - "
            f"{str(self.end.hour).rjust(2, '0')}:{str(self.end.minute).rjust(2, '0')}"
        )


class PairSchema(BaseModel):
    """Учебная пара с полной информацией"""

    date: str
    day: str
    number: int
    pair_time: PairTimeSchema
    pair_type: str
    group: str
    discipline: str
    teacher: str
    classroom: str | None = None

    @field_validator("number")
    @classmethod
    def validate_pair_number(cls, v):
        if not 1 <= v <= 6:
            msg = "Номер пары должен быть от 1 до 6"
            raise ValueError(msg)
        return v


class TeacherSchema(BaseModel):
    """Преподаватель с дисциплинами и группами"""

    name: str
    disciplines: set[str]
    groups: set[str]


class TeachersScheduleSchema(BaseModel):
    """Расписание преподавателя на неделю"""

    Понедельник: list[bool]
    Вторник: list[bool]
    Среда: list[bool]
    Четверг: list[bool]
    Пятница: list[bool]
    Суббота: list[bool]
    Воскресенье: list[bool]

    @field_validator(
        "Понедельник",
        "Вторник",
        "Среда",
        "Четверг",
        "Пятница",
        "Суббота",
        "Воскресенье",
    )
    @classmethod
    def validate_day_schedule(cls, v):
        if len(v) < 6:
            msg = "Расписание на день должно содержать минимум 6 пар"
            raise ValueError(msg)
        # Обрезаем до 6 если больше
        return v[:6] if len(v) > 6 else v

    def get_pair_number(
        self, pair_time: PairTimeSchema, schedule_time: dict[int, tuple]
    ) -> int | None:
        """Получить номер пары по времени"""
        for number, (start, end) in schedule_time.items():
            if pair_time.start <= end and pair_time.end >= start:
                return number
        return None

    def take_pair(self, day: str, pair_number: int) -> None:
        """Занять время для пары"""
        day_schedule = getattr(self, day)
        day_schedule[pair_number - 1] = False

    def free_pair(self, day: str, pair_number: int) -> None:
        """Освободить время для пары"""
        day_schedule = getattr(self, day)
        day_schedule[pair_number - 1] = True

    def choose_pair(
        self, day: str, pair_time: PairTimeSchema, schedule_time: dict[int, tuple]
    ) -> None:
        """Выбрать время для пары"""
        pair_number = self.get_pair_number(pair_time, schedule_time)
        if pair_number is None:
            msg = f"Невозможно выбрать время '{pair_time}'"
            raise ValueError(msg)
        day_schedule = getattr(self, day)
        if not day_schedule[pair_number - 1]:
            msg = f"Время '{pair_time}' занято или недоступно"
            raise ValueError(msg)
        self.take_pair(day, pair_number)


class RoomScheduleSchema(BaseModel):
    """Расписание аудитории на неделю"""

    Понедельник: list[bool]
    Вторник: list[bool]
    Среда: list[bool]
    Четверг: list[bool]
    Пятница: list[bool]
    Суббота: list[bool]
    Воскресенье: list[bool]

    @field_validator(
        "Понедельник",
        "Вторник",
        "Среда",
        "Четверг",
        "Пятница",
        "Суббота",
        "Воскресенье",
    )
    @classmethod
    def validate_day_schedule(cls, v):
        if len(v) < 6:
            msg = "Расписание на день должно содержать минимум 6 пар"
            raise ValueError(msg)
        # Обрезаем до 6 если больше
        return v[:6] if len(v) > 6 else v

    def get_pair_number(
        self, pair_time: PairTimeSchema, schedule_time: dict[int, tuple]
    ) -> int | None:
        """Получить номер пары по времени"""
        for number, (start, end) in schedule_time.items():
            if pair_time.start <= end and pair_time.end >= start:
                return number
        return None


class RoomSchema(BaseModel):
    """Тип аудитории"""

    is_online: bool = False


class DataSchema(BaseModel):
    """Контейнер всех параметров расписания"""

    counter: int
    days: list[str]
    teachers_schedule_time: dict[int, tuple]
    schedule_time_shift_1: dict[int, PairTimeSchema]
    schedule_time_shift_2: dict[int, PairTimeSchema]
    schedule_time_shift_3: dict[int, PairTimeSchema]
    groups_shift: dict[str, dict[int, PairTimeSchema]]
    discipline_hours: dict[str, dict[str, int]]
    teachers: dict[str, list[TeacherSchema]]
    teachers_work_hours: dict[str, TeachersScheduleSchema]
    rooms: dict[str, RoomSchema]
    rooms_availability_hours: dict[str, RoomScheduleSchema]

    @field_validator("teachers_schedule_time")
    @classmethod
    def validate_schedule_time(cls, v):  # noqa: ANN001
        """Валидация временных интервалов пар"""
        for number, (start, end) in v.items():
            if start >= end:
                msg = f"Некорректный временной интервал для пары {number}"
                raise ValueError(msg)
        return v
