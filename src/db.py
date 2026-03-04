"""
Модуль содержит структуры данных, классы и функции, используемые для хранения,
описания и сериализации параметров учебного расписания. Обеспечивает базовый
набор объектов: временные интервалы пар, сами пары, преподаватели, их рабочие
часы, аудитории и доступность помещений.

Основные компоненты:

Классы:
---------
- PairTime — временной интервал учебной пары с типом (онлайн/офлайн).
- Pair — объект учебной пары с датой, днём недели, номером, временем и всей
         сопутствующей информацией (дисциплина, группа, преподаватель, аудитория).
- Teacher — преподаватель со списком дисциплин и доступных групп.
- TeachersSchedule — модель расписания преподавателя на неделю, позволяющая
                     отмечать занятые и свободные слоты.
- RoomSchedule — аналогичное расписание для аудиторий.
- Room — тип аудитории (онлайн или офлайн).
- Data (абстрактный класс) — базовый контейнер всех параметров расписания.
- EmptyData — пустая реализация контейнера.
- ExampleData — пример заполненного набора данных для тестов.

Константы:
-----------
- offline_str, online_str — текстовые обозначения форматов занятий.
- days, workweek_days — списки дней недели.
- teachers_schedule_time — словарь с нормативными временными интервалами пар.

Функции:
---------
- save_data(data) — сериализация и сохранение объекта данных в файл.
- load_data() — загрузка сохранённых данных.
- check_exists_data() — проверка наличия файла базы.
- resource_path(relative_path) — безопасное получение пути ресурса (PyInstaller).
- get_data_file_path() — путь к каталогу хранения данных в домашней директории.

Назначение модуля:
-------------------
Файл представляет собой основу внутреннего формата данных для системы составления
расписания. Все алгоритмы генерации, проверки и оптимизации расписания работают
на основе структур, определённых здесь.
"""

import json
import os
import sys
from abc import ABC, abstractmethod
from datetime import time, timedelta
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

from config.logger import get_logger

logger = get_logger("db")

from config.constants import (
    DAYS,
    DB_FILE,
    DB_PATH_NAME,
    MAX_PAIR_NUMBER,
    MIN_PAIR_NUMBER,
    PAIRS_PER_DAY,
    TEACHERS_SCHEDULE_TIME,
    PairType,
    RoomPrefix,
)
from src.schemas import (
    DataSchema,
    PairSchema,
    PairTimeSchema,
    RoomScheduleSchema,
    RoomSchema,
    TeacherSchema,
    TeachersScheduleSchema,
)

# region Classes


class PairTime:  # pair: start, end, pair_type
    def __init__(self, start: time, end: time, pair_type: str):
        self.start = start
        self.end = end or start + timedelta(hours=1, minutes=30)
        self.pair_type = pair_type

    def __repr__(self):
        return f"({self.start}-{self.end}, {self.pair_type})"

    def get_str(self):
        return (
            f"{str(self.start.hour).rjust(2, '0')}:{str(self.start.minute).rjust(2, '0')} - "
            f"{str(self.end.hour).rjust(2, '0')}:{str(self.end.minute).rjust(2, '0')}"
        )


class Pair:  # pair: date, day, number, pair_time, pair_type, group, teacher, classroom
    def __init__(
        self,
        date: str,
        day: str,
        number: int,
        pair_time: PairTime,
        pair_type: str,
        group: str,
        discipline: str,
        teacher: str,
        classroom: str,
    ):
        self.date = date
        self.day = day
        self.number = number
        self.pair_time = pair_time
        self.pair_type = pair_type
        self.group = group
        self.discipline = discipline
        self.teacher = teacher
        self.classroom = classroom

    def __repr__(self):
        return f"{self.date} | {self.day} | {self.number} | {self.pair_time} | {self.pair_type} | {self.discipline} | {self.teacher} | {self.classroom}"


class Teacher:  # teacher: name, disciplines, groups
    def __init__(self, name: str, disciplines: set, groups: set):
        self.name = name
        self.disciplines = disciplines
        self.groups = groups

    def __repr__(self):
        return f"({self.name}|{self.disciplines}|{self.groups})"


class TeachersSchedule:  # teachers_schedule: day, pairs
    """
    Возвращает объект расписания преподавателя для каждого дня недели

    Один день недели это список пар из 6 слотов, например (True, False, True, True, True, True), None - день не свободен

    True - Пара свободна, False - Пара занята или пару нельзя поставить на это время

    :param mon: Понедельник
    :param tue: Вторник
    :param wed: Среда
    :param thu: Четверг
    :param fri: Пятница
    :param sat: Суббота
    :param sun: Воскресенье
    """

    def __init__(
        self,
        mon: list[bool] = None,
        tue: list[bool] = None,
        wed: list[bool] = None,
        thu: list[bool] = None,
        fri: list[bool] = None,
        sat: list[bool] = None,
        sun: list[bool] = None,
    ):
        self.schedule_for_days = {
            "Понедельник": None if mon is None else list(mon),
            "Вторник": None if tue is None else list(tue),
            "Среда": None if wed is None else list(wed),
            "Четверг": None if thu is None else list(thu),
            "Пятница": None if fri is None else list(fri),
            "Суббота": None if sat is None else list(sat),
            "Воскресенье": None if sun is None else list(sun),
        }
        for day in self.schedule_for_days:
            if self.schedule_for_days[day] is None:
                self.schedule_for_days[day] = [False] * PAIRS_PER_DAY
            while len(self.schedule_for_days[day]) < PAIRS_PER_DAY:
                self.schedule_for_days[day].append(False)

    @staticmethod
    def get_pair_number(pair_time: PairTime) -> int | None:
        # Get number from teachers_schedule_time
        for number, (start, end) in TEACHERS_SCHEDULE_TIME.items():
            # print(f"{start} <= {pair_time} <= {end}: {pair_time.start <= end and pair_time.end >= start}")
            # Check if the pair_time overlaps with the scheduled time
            if pair_time.start <= end and pair_time.end >= start:  # M
                return number
        return None

    def take_pair(self, day: str, pair_number: int) -> None:
        self.schedule_for_days[day][pair_number - 1] = False

    def free_pair(self, day: str, pair_number: int) -> None:
        self.schedule_for_days[day][pair_number - 1] = True

    def choose_pair(self, day: str, pair_time: PairTime):
        pair_number = self.get_pair_number(pair_time)
        if pair_number is None:
            msg = f"Невозможно выбрать время '{pair_time}'"
            raise ValueError(msg)
        if not self.schedule_for_days[day][pair_number - 1]:
            msg = f"Время '{pair_time}' занято или недоступно"
            raise ValueError(msg)
        self.take_pair(day, pair_number)

    def __repr__(self):
        str_list = []
        for day in self.schedule_for_days:
            s = f"{day[:2]}:"
            for b in self.schedule_for_days[day]:
                s += "X" if b else "O"
            str_list.append(s)
        return "[" + ", ".join(str_list) + "]"


class RoomSchedule:
    """
    False - Аудитория свободна
    True - Аудитория занята или пару нельзя поставить на это время
    """

    def __init__(
        self,
        mon: list[bool] = None,
        tue: list[bool] = None,
        wed: list[bool] = None,
        thu: list[bool] = None,
        fri: list[bool] = None,
        sat: list[bool] = None,
        sun: list[bool] = None,
    ):
        self.schedule_for_days = {
            "Понедельник": None if mon is None else list(mon),
            "Вторник": None if tue is None else list(tue),
            "Среда": None if wed is None else list(wed),
            "Четверг": None if thu is None else list(thu),
            "Пятница": None if fri is None else list(fri),
            "Суббота": None if sat is None else list(sat),
            "Воскресенье": None if sun is None else list(sun),
        }
        for day in self.schedule_for_days:
            if self.schedule_for_days[day] is None:
                self.schedule_for_days[day] = [False] * PAIRS_PER_DAY
            while len(self.schedule_for_days[day]) < PAIRS_PER_DAY:
                self.schedule_for_days[day].append(False)

    @staticmethod
    def get_pair_number(pair_time: PairTime) -> int | None:
        for number, (start, end) in TEACHERS_SCHEDULE_TIME.items():
            if pair_time.start <= end and pair_time.end >= start:
                return number
        return None

    def __repr__(self):
        return str(self.schedule_for_days)


class Room:
    def __init__(self, is_online: bool = False) -> None:
        self.is_online = is_online


# endregion


# region Constants

# Удалены - перенесены в config.constants

# endregion


# region Data


class Data(ABC):
    @abstractmethod
    def __init__(self):
        raise NotImplementedError

    counter: int
    days: list = DAYS
    teachers_schedule_time: dict = TEACHERS_SCHEDULE_TIME
    schedule_time_shift_1: dict[int, PairTime]
    schedule_time_shift_2: dict[int, PairTime]
    schedule_time_shift_3: dict[int, PairTime]
    groups_shift: dict[str, dict[int, PairTime]]
    discipline_hours: dict[str, dict[str, int]]
    teachers: dict[str, list[Teacher]]
    teachers_work_hours: dict[str, TeachersSchedule]
    rooms: dict[str, Room]
    rooms_availability_hours: dict[str, RoomSchedule]


class EmptyData(Data):
    def __init__(self):
        self.counter = 1
        self.days = DAYS
        self.teachers_schedule_time = TEACHERS_SCHEDULE_TIME
        self.schedule_time_shift_1 = {}
        self.schedule_time_shift_2 = {}
        self.schedule_time_shift_3 = {}
        self.groups_shift = {}
        self.discipline_hours = {}
        self.teachers = {}
        self.teachers_work_hours = {}
        self.rooms = {}
        self.rooms_availability_hours = {}


class ExampleData(Data):
    def __init__(self):
        self.counter = 1

        self.days = DAYS

        self.teachers_schedule_time = TEACHERS_SCHEDULE_TIME

        self.schedule_time_shift_1 = {  # time schedule for first shift
            1: PairTime(time(8, 0), time(9, 30), PairType.OFFLINE.value),
            2: PairTime(time(9, 40), time(11, 10), PairType.OFFLINE.value),
            3: PairTime(time(16, 40), time(17, 40), PairType.ONLINE.value),
        }

        self.schedule_time_shift_2 = {  # time schedule for second shift
            1: PairTime(time(8, 0), time(9, 0), PairType.ONLINE.value),
            2: PairTime(time(11, 30), time(13, 0), PairType.OFFLINE.value),
            3: PairTime(time(13, 10), time(14, 40), PairType.OFFLINE.value),
        }

        self.schedule_time_shift_3 = {  # time schedule for third shift
            1: PairTime(time(11, 50), time(12, 50), PairType.ONLINE.value),
            2: PairTime(time(15, 0), time(16, 30), PairType.OFFLINE.value),
            3: PairTime(time(16, 40), time(18, 10), PairType.OFFLINE.value),
        }

        self.groups_shift = {
            "П9024": self.schedule_time_shift_1,
            "П9022": self.schedule_time_shift_2,
            "П9021": self.schedule_time_shift_3,
        }

        # Создаем правильное расписание для групп согласно вашим данным
        # П9024: пары 1, 2, 3 (08:00-09:00, 11:30-13:00, 13:10-14:40)
        # П9022: пары 1, 2, 3 (08:00-09:00, 11:30-13:00, 13:10-14:40)
        # П9021: пары 1, 2, 3 (11:50-12:50, 15:00-16:30, 16:40-18:10)

        # Переопределяем расписание групп согласно вашим данным
        custom_schedule_1 = {
            1: PairTime(time(8, 0), time(9, 30), PairType.OFFLINE.value),  # Смена 1
            2: PairTime(time(11, 30), time(13, 0), PairType.OFFLINE.value),
            3: PairTime(time(13, 10), time(14, 40), PairType.OFFLINE.value),
        }

        custom_schedule_2 = {
            1: PairTime(time(8, 0), time(9, 0), PairType.OFFLINE.value),  # Смена 2
            2: PairTime(time(11, 30), time(13, 0), PairType.OFFLINE.value),
            3: PairTime(time(13, 10), time(14, 40), PairType.OFFLINE.value),
        }

        custom_schedule_3 = {
            1: PairTime(time(11, 50), time(12, 50), PairType.ONLINE.value),  # Смена 3
            2: PairTime(time(15, 0), time(16, 30), PairType.OFFLINE.value),
            3: PairTime(time(16, 40), time(18, 10), PairType.OFFLINE.value),
        }

        self.groups_shift = {
            "П9024": custom_schedule_1,
            "П9022": custom_schedule_2,
            "П9021": custom_schedule_3,
        }

        self.discipline_hours = {  # on current week
            "П9024": {
                "Литература": 2,
                "Физика": 0,
                "Иностранный язык": 2,
                "Математика": 4,
                "Физическая культура": 2,
                "Основы безопасности жизнедеятельности": 0,
                "Информатика": 2,
                "География": 4,
                "Биология": 2,
                "Химия": 0,
                "Русский язык": 2,
                "Обществознание": 4,
                "История": 2,
                "Индивидуальный проект": 0,
                "Право": 2,
            },
            "П9022": {
                "Литература": 2,
                "Физика": 0,
                "Иностранный язык": 2,
                "Математика": 4,
                "Физическая культура": 2,
                "Основы безопасности жизнедеятельности": 0,
                "Информатика": 2,
                "География": 4,
                "Биология": 2,
                "Химия": 0,
                "Русский язык": 2,
                "Обществознание": 4,
                "История": 2,
                "Индивидуальный проект": 0,
                "Право": 2,
            },
            "П9021": {
                "Литература": 2,
                "Физика": 0,
                "Иностранный язык": 2,
                "Математика": 4,
                "Физическая культура": 2,
                "Основы безопасности жизнедеятельности": 0,
                "Информатика": 2,
                "География": 4,
                "Биология": 2,
                "Химия": 0,
                "Русский язык": 2,
                "Обществознание": 4,
                "История": 2,
                "Индивидуальный проект": 0,
                "Право": 2,
            },
        }

        self.teachers = {  # random teachers
            "Дмитриев Д.Д.": [
                Teacher(
                    "Дмитриев Д.Д.", {"Информатика", "Индивидуальный проект"}, {"П9024"}
                )
            ],
            "Александров А.А.": [
                Teacher("Александров А.А.", {"Математика"}, {"П9024"})
            ],
            "Иванов И.И.": [
                Teacher(
                    "Иванов И.И.",
                    {"Математика", "Физика", "Информатика", "Индивидуальный проект"},
                    {"П9022", "П9021"},
                )
            ],
            "Петрова П.П.": [
                Teacher("Петрова П.П.", {"Литература", "Русский язык"}, {"П9022"})
            ],
            "Владимирова В.П.": [
                Teacher("Владимирова В.П.", {"Литература", "Русский язык"}, {"П9021"})
            ],
            "Данилова Д.Д.": [
                Teacher("Данилова Д.Д.", {"Литература", "Русский язык"}, {"П9024"})
            ],
            "Сидорова С.С.": [
                Teacher(
                    "Сидорова С.С.",
                    {"География", "Биология", "Химия"},
                    {"П9022", "П9021", "П9024"},
                )
            ],
            "Кузнецова К.К.": [
                Teacher(
                    "Кузнецова К.К.",
                    {"Обществознание", "История", "Право"},
                    {"П9021", "П9022", "П9024"},
                )
            ],
            "Васильев В.В.": [
                Teacher(
                    "Васильев В.В.",
                    {"Физическая культура", "Основы безопасности жизнедеятельности"},
                    {"П9021", "П9022", "П9024"},
                )
            ],
            "Смирнова С.С.": [
                Teacher("Смирнова С.С.", {"Иностранный язык"}, {"П9024"})
            ],
            "Смирнов В.С.": [
                Teacher("Смирнов В.С.", {"Иностранный язык"}, {"П9022", "П9021"})
            ],
        }

        self.teachers_work_hours = {  # on current week
            "Дмитриев Д.Д.": TeachersSchedule(
                mon=(True, True, True, True, True, True, True),
                thu=(True, True, True, True, True, True, True),
                fri=(True, True, True, True, True, True, True),
            ),
            "Александров А.А.": TeachersSchedule(
                mon=(True, True, True, True, True, True, True),
                tue=(True, True, True, True, True, True, True),
                wed=(True, True, True, True, True, True, True),
                thu=(True, True, True, True, True, True, True),
                fri=(True, True, True, True, True, True, True),
            ),
            "Иванов И.И.": TeachersSchedule(
                mon=(True, True, True, True, True, True, True),
                wed=(True, True, True, True, True, True, True),
                thu=(True, True, True, True, True, True, True),
                fri=(True, True, True, True, True, True, True),
            ),
            "Петрова П.П.": TeachersSchedule(
                mon=(True, True, True, True, True, True, True),
                tue=(True, True, True, True, True, True, True),
                wed=(True, True, True, True, True, True, True),
            ),
            "Владимирова В.П.": TeachersSchedule(
                mon=(True, True, True, True, True, True, True),
                tue=(True, True, True, True, True, True, True),
            ),
            "Данилова Д.Д.": TeachersSchedule(
                mon=(True, True, True, True, True, True, True),
                tue=(True, True, True, True, True, True, True),
                fri=(True, True, True, True, True, True, True),
            ),
            "Сидорова С.С.": TeachersSchedule(
                mon=(True, True, True, True, True, True, True),
                tue=(True, True, True, True, True, True, True),
                wed=(True, True, True, True, True, True, True),
                thu=(True, True, True, True, True, True, True),
                fri=(True, True, True, True, True, True, True),
            ),
            "Кузнецова К.К.": TeachersSchedule(
                mon=(True, True, True, True, True, True, True),
                wed=(True, True, True, True, True, True, True),
                thu=(True, True, True, True, True, True, True),
                fri=(True, True, True, True, True, True, True),
            ),
            "Васильев В.В.": TeachersSchedule(
                mon=(True, True, True, True, True, True, True),
                thu=(True, True, True, True, True, True, True),
                fri=(True, True, True, True, True, True, True),
            ),
            "Смирнова С.С.": TeachersSchedule(
                wed=(True, True, True, True, True, True, True),
                thu=(True, True, True, True, True, True, True),
                fri=(True, True, True, True, True, True, True),
            ),
            "Смирнов В.С.": TeachersSchedule(
                mon=(True, True, True, True, True, True, True),
                fri=(True, True, True, True, True, True, True),
            ),
        }

        self.rooms = {
            "К1": Room(),
            "К2": Room(),
            "К3": Room(),
            "Д1": Room(True),
            "Д2": Room(True),
            "Д3": Room(True),
        }

        self.rooms_availability_hours = {
            "К1": RoomSchedule(),
            "К2": RoomSchedule(),
            "К3": RoomSchedule(),
            "Д1": RoomSchedule(),
            "Д2": RoomSchedule(),
            "Д3": RoomSchedule(),
        }


# region SQLAlchemy Models

Base = declarative_base()


class TeacherModel(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    disciplines = Column(Text, nullable=False)  # JSON сериализация set
    groups = Column(Text, nullable=False)  # JSON сериализация set

    # Связь с расписанием
    schedules = relationship(
        "TeacherScheduleModel", back_populates="teacher", cascade="all, delete-orphan"
    )

    def to_teacher(self):
        """Конвертация в объект Teacher"""
        import json

        return Teacher(
            name=self.name,
            disciplines=set(json.loads(self.disciplines)),
            groups=set(json.loads(self.groups)),
        )


# region SQLAlchemy Models (Improved)

Base = declarative_base()


class TeacherModel(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    disciplines = Column(Text, nullable=False)  # JSON сериализация set
    groups = Column(Text, nullable=False)  # JSON сериализация set

    # Связь с расписанием (один преподаватель -> много записей расписания)
    schedules = relationship(
        "TeacherScheduleModel", back_populates="teacher", cascade="all, delete-orphan"
    )

    def to_teacher(self):
        """Конвертация в объект Teacher"""
        import json

        return Teacher(
            name=self.name,
            disciplines=set(json.loads(self.disciplines)),
            groups=set(json.loads(self.groups)),
        )


class TeacherScheduleModel(Base):
    __tablename__ = "teachers_schedule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    teacher_id = Column(
        Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False
    )
    day = Column(String, nullable=False)  # день недели
    pair_number = Column(Integer, nullable=False)  # номер пары (1-6)
    is_free = Column(Boolean, default=True)  # True - свободно, False - занято

    # Связь с преподавателем
    teacher = relationship("TeacherModel", back_populates="schedules")

    __table_args__ = (
        # Уникальность: один преподаватель не может иметь две записи для одного дня и пары
        UniqueConstraint(
            "teacher_id", "day", "pair_number", name="unique_teacher_day_pair"
        ),
    )


class RoomModel(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    is_online = Column(Boolean, default=False)

    # Связь с расписанием
    schedules = relationship(
        "RoomScheduleModel", back_populates="room", cascade="all, delete-orphan"
    )


class RoomScheduleModel(Base):
    __tablename__ = "rooms_schedule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(
        Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    day = Column(String, nullable=False)
    pair_number = Column(Integer, nullable=False)  # номер пары (1-6)
    is_available = Column(Boolean, default=True)  # True - доступно, False - занято

    # Связь с аудиторией
    room = relationship("RoomModel", back_populates="schedules")

    __table_args__ = (
        # Уникальность: одна аудитория не может иметь две записи для одного дня и пары
        UniqueConstraint("room_id", "day", "pair_number", name="unique_room_day_pair"),
    )


class GroupModel(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    shift_number = Column(Integer, nullable=False)  # 1, 2, or 3

    # Связи
    discipline_hours = relationship(
        "DisciplineHoursModel", back_populates="group", cascade="all, delete-orphan"
    )
    shift_pairs = relationship(
        "GroupShiftPairModel", back_populates="group", cascade="all, delete-orphan"
    )


class GroupShiftPairModel(Base):
    __tablename__ = "groups_shift_pairs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    pair_number = Column(Integer, nullable=False)
    start_time = Column(String, nullable=False)  # HH:MM:SS
    end_time = Column(String, nullable=False)
    pair_type = Column(String, nullable=False)

    # Связь с группой
    group = relationship("GroupModel", back_populates="shift_pairs")

    __table_args__ = (
        UniqueConstraint("group_id", "pair_number", name="unique_group_pair"),
    )


class ShiftTimeModel(Base):
    __tablename__ = "shift_times"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shift_number = Column(Integer, nullable=False)  # 1, 2, or 3
    pair_number = Column(Integer, nullable=False)
    start_time = Column(String, nullable=False)  # HH:MM:SS
    end_time = Column(String, nullable=False)
    pair_type = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("shift_number", "pair_number", name="unique_shift_pair"),
    )


class DisciplineHoursModel(Base):
    __tablename__ = "discipline_hours"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    discipline_name = Column(String, nullable=False)
    hours = Column(Integer, nullable=False)

    # Связь с группой
    group = relationship("GroupModel", back_populates="discipline_hours")

    __table_args__ = (
        UniqueConstraint("group_id", "discipline_name", name="unique_group_discipline"),
    )


class MainDataModel(Base):
    __tablename__ = "main_data"

    id = Column(Integer, primary_key=True, default=1)
    counter = Column(Integer, default=1)


# endregion

# endregion


# region SQLAlchemy Database Functions


def get_sqlite_db_path() -> str:
    """Получение пути к файлу SQLite базы данных"""
    data_path = get_data_file_path()
    if isinstance(data_path, Path):
        db_path = data_path.with_suffix(".db")
    else:
        db_path = data_path.replace(".pickle", ".db")
    return str(db_path)


# Глобальные переменные для SQLAlchemy
engine = None
SessionLocal = None


def init_db():
    """Инициализация SQLAlchemy базы данных"""
    global engine, SessionLocal

    db_path = get_sqlite_db_path()
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    SessionLocal = sessionmaker(bind=engine)

    # Создаем все таблицы
    Base.metadata.create_all(bind=engine)

    # Создаем начальную запись если ее нет
    session = SessionLocal()
    try:
        main_data = session.query(MainDataModel).filter_by(id=1).first()
        if not main_data:
            main_data = MainDataModel(id=1, counter=1)
            session.add(main_data)
            session.commit()
    finally:
        session.close()


def get_db_session():
    """Получение сессии базы данных"""
    if SessionLocal is None:
        init_db()
    return SessionLocal()


# region SQLAlchemy Database Functions (Improved)


def save_data_sqlalchemy(data) -> None:
    """Сохранение данных с использованием SQLAlchemy + Pydantic схемы"""
    logger.info("Сохранение данных в SQLAlchemy базу")
    logger.debug(
        f"Сохраняем данные: counter={data.counter}, групп={len(data.discipline_hours)}, преподавателей={len(data.teachers)}"
    )

    if SessionLocal is None:
        init_db()

    session = get_db_session()
    try:
        # Обновляем счетчик
        main_data = session.query(MainDataModel).filter_by(id=1).first()
        if main_data:
            main_data.counter = data.counter + 1
        else:
            main_data = MainDataModel(id=1, counter=data.counter + 1)
            session.add(main_data)

        # Очищаем существующие данные (в правильном порядке из-за ForeignKey)
        session.query(TeacherScheduleModel).delete()
        session.query(TeacherModel).delete()
        session.query(RoomScheduleModel).delete()
        session.query(RoomModel).delete()
        session.query(DisciplineHoursModel).delete()
        session.query(GroupShiftPairModel).delete()
        session.query(GroupModel).delete()
        session.query(ShiftTimeModel).delete()

        # Сохраняем преподавателей
        teachers_map = {}  # имя -> id
        for teacher_list in data.teachers.values():
            for teacher in teacher_list:
                teacher_schema = TeacherSchema(
                    name=teacher.name,
                    disciplines=list(teacher.disciplines),
                    groups=list(teacher.groups),
                )

                teacher_model = TeacherModel(
                    name=teacher_schema.name,
                    disciplines=json.dumps(
                        list(teacher_schema.disciplines), ensure_ascii=False
                    ),
                    groups=json.dumps(list(teacher_schema.groups), ensure_ascii=False),
                )
                session.add(teacher_model)
                session.flush()  # чтобы получить id
                teachers_map[teacher.name] = teacher_model.id

                # Сохраняем расписание преподавателя
                if teacher.name in data.teachers_work_hours:
                    schedule = data.teachers_work_hours[teacher.name]
                    for day, day_schedule in schedule.schedule_for_days.items():
                        for pair_num, is_free in enumerate(day_schedule, 1):
                            schedule_model = TeacherScheduleModel(
                                teacher_id=teacher_model.id,
                                day=day,
                                pair_number=pair_num,
                                is_free=is_free,
                            )
                            session.add(schedule_model)

        # Сохраняем аудитории
        rooms_map = {}  # имя -> id
        for room_name, room_schedule in data.rooms_availability_hours.items():
            is_online = room_name.startswith(
                RoomPrefix.DIGITAL.value
            )  # Д - онлайн аудитории

            room_model = RoomModel(name=room_name, is_online=is_online)
            session.add(room_model)
            session.flush()
            rooms_map[room_name] = room_model.id

            # Сохраняем расписание аудитории
            for day, day_schedule in room_schedule.schedule_for_days.items():
                for pair_num, is_available in enumerate(day_schedule, 1):
                    schedule_model = RoomScheduleModel(
                        room_id=room_model.id,
                        day=day,
                        pair_number=pair_num,
                        is_available=is_available,
                    )
                    session.add(schedule_model)

        # Сохраняем группы
        groups_map = {}  # имя -> id
        for group_name, shift_dict in data.groups_shift.items():
            # Определяем номер смены по расписанию группы
            shift_number = 1  # значение по умолчанию

            # Проверяем по первой паре в расписании группы
            if shift_dict and 1 in shift_dict:
                first_pair = shift_dict[1]

                # Сравниваем время начала первой пары с эталонными расписаниями
                if (
                    hasattr(data, "schedule_time_shift_1")
                    and 1 in data.schedule_time_shift_1
                    and first_pair.start == data.schedule_time_shift_1[1].start
                    and first_pair.end == data.schedule_time_shift_1[1].end
                ):
                    shift_number = 1
                elif (
                    hasattr(data, "schedule_time_shift_2")
                    and 1 in data.schedule_time_shift_2
                    and first_pair.start == data.schedule_time_shift_2[1].start
                    and first_pair.end == data.schedule_time_shift_2[1].end
                ):
                    shift_number = 2
                elif (
                    hasattr(data, "schedule_time_shift_3")
                    and 1 in data.schedule_time_shift_3
                    and first_pair.start == data.schedule_time_shift_3[1].start
                    and first_pair.end == data.schedule_time_shift_3[1].end
                ):
                    shift_number = 3

            group_model = GroupModel(name=group_name, shift_number=shift_number)
            session.add(group_model)
            session.flush()
            groups_map[group_name] = group_model.id

            # Сохраняем расписание пар для группы
            for pair_number, pair_time in shift_dict.items():
                shift_pair_model = GroupShiftPairModel(
                    group_id=group_model.id,
                    pair_number=pair_number,
                    start_time=pair_time.start.strftime("%H:%M:%S"),
                    end_time=pair_time.end.strftime("%H:%M:%S"),
                    pair_type=pair_time.pair_type,
                )
                session.add(shift_pair_model)

        # Сохраняем discipline_hours
        for group_name, disciplines in data.discipline_hours.items():
            if group_name in groups_map:
                for discipline_name, hours in disciplines.items():
                    discipline_model = DisciplineHoursModel(
                        group_id=groups_map[group_name],
                        discipline_name=discipline_name,
                        hours=hours,
                    )
                    session.add(discipline_model)

        # Сохраняем schedule_time_shift
        for shift_name, shift_dict in [
            ("schedule_time_shift_1", data.schedule_time_shift_1),
            ("schedule_time_shift_2", data.schedule_time_shift_2),
            ("schedule_time_shift_3", data.schedule_time_shift_3),
        ]:
            if hasattr(data, shift_name) and shift_dict:
                shift_number = int(shift_name.split("_")[-1])
                for pair_number, pair_time in shift_dict.items():
                    time_shift_model = ShiftTimeModel(
                        shift_number=shift_number,
                        pair_number=pair_number,
                        start_time=pair_time.start.strftime("%H:%M:%S"),
                        end_time=pair_time.end.strftime("%H:%M:%S"),
                        pair_type=pair_time.pair_type,
                    )
                    session.add(time_shift_model)

        session.commit()
        logger.info(
            f"Данные успешно сохранены: групп={len(data.discipline_hours)}, преподавателей={len(data.teachers)}, аудиторий={len(data.rooms)}"
        )

    except Exception as e:
        session.rollback()
        logger.exception(f"Ошибка при сохранении данных: {e}")
        raise
    finally:
        session.close()


def load_data_sqlalchemy() -> Data:
    """Загрузка данных с использованием SQLAlchemy + Pydantic схемы"""
    logger.info("Загрузка данных из SQLAlchemy базы")

    if SessionLocal is None:
        init_db()

    session = get_db_session()
    try:
        # Проверяем, есть ли данные
        teacher_count = session.query(TeacherModel).count()
        if teacher_count == 0:
            logger.info("База данных пуста, создаем пример данных")
            session.close()
            example_data = ExampleData()
            save_data_sqlalchemy(example_data)
            return example_data

        logger.debug(f"В базе найдено преподавателей: {teacher_count}")

        # Создаем объект данных
        data = EmptyData()

        # Загружаем счетчик
        main_data = session.query(MainDataModel).filter_by(id=1).first()
        data.counter = main_data.counter if main_data else 1
        logger.debug(f"Загружен счетчик запусков: {data.counter}")

        # Загружаем преподавателей и их расписание
        teacher_models = session.query(TeacherModel).all()
        data.teachers = {}
        data.teachers_work_hours = {}

        logger.debug(f"Загрузка {len(teacher_models)} преподавателей...")

        for i, teacher_model in enumerate(teacher_models, 1):
            logger.debug(
                f"Загрузка преподавателя {i}/{len(teacher_models)}: {teacher_model.name}"
            )
            teacher_schema = TeacherSchema(
                name=teacher_model.name,
                disciplines=set(json.loads(teacher_model.disciplines)),
                groups=set(json.loads(teacher_model.groups)),
            )

            teacher = Teacher(
                name=teacher_schema.name,
                disciplines=teacher_schema.disciplines,
                groups=teacher_schema.groups,
            )

            if teacher.name not in data.teachers:
                data.teachers[teacher.name] = []
            data.teachers[teacher.name].append(teacher)

            # Создаем расписание преподавателя
            teachers_schedule = TeachersSchedule()

            # Загружаем расписание из БД
            schedule_models = (
                session.query(TeacherScheduleModel)
                .filter_by(teacher_id=teacher_model.id)
                .all()
            )
            for schedule_model in schedule_models:
                # Проверяем, что день существует в расписании
                if schedule_model.day not in teachers_schedule.schedule_for_days:
                    logger.warning(
                        f"Неизвестный день '{schedule_model.day}' для преподавателя {teacher.name}"
                    )
                    continue

                # Инициализируем день если нужно
                if teachers_schedule.schedule_for_days[schedule_model.day] is None:
                    teachers_schedule.schedule_for_days[schedule_model.day] = [
                        False
                    ] * PAIRS_PER_DAY

                # Проверяем границы номера пары
                if not MIN_PAIR_NUMBER <= schedule_model.pair_number <= MAX_PAIR_NUMBER:
                    logger.warning(
                        f"Некорректный номер пары {schedule_model.pair_number} для преподавателя {teacher.name}"
                    )
                    continue

                # Устанавливаем значение
                teachers_schedule.schedule_for_days[schedule_model.day][
                    schedule_model.pair_number - 1
                ] = schedule_model.is_free

            data.teachers_work_hours[teacher.name] = teachers_schedule

        # Загружаем аудитории и их расписание
        room_models = session.query(RoomModel).all()
        data.rooms_availability_hours = {}
        data.rooms = {}

        for room_model in room_models:
            room_schedule = RoomSchedule()

            # Загружаем расписание из БД
            schedule_models = (
                session.query(RoomScheduleModel).filter_by(room_id=room_model.id).all()
            )
            for schedule_model in schedule_models:
                # Проверяем, что день существует в расписании
                if schedule_model.day not in room_schedule.schedule_for_days:
                    logger.warning(
                        f"Неизвестный день '{schedule_model.day}' для аудитории {room_model.name}"
                    )
                    continue

                if room_schedule.schedule_for_days[schedule_model.day] is None:
                    room_schedule.schedule_for_days[schedule_model.day] = [
                        False
                    ] * PAIRS_PER_DAY

                # Проверяем границы номера пары
                if not MIN_PAIR_NUMBER <= schedule_model.pair_number <= MAX_PAIR_NUMBER:
                    logger.warning(
                        f"Некорректный номер пары {schedule_model.pair_number} для аудитории {room_model.name}"
                    )
                    continue

                room_schedule.schedule_for_days[schedule_model.day][
                    schedule_model.pair_number - 1
                ] = not schedule_model.is_available

            data.rooms_availability_hours[room_model.name] = room_schedule
            data.rooms[room_model.name] = Room(is_online=room_model.is_online)

        # Загружаем группы и их расписание
        group_models = session.query(GroupModel).all()
        data.groups_shift = {}
        data.discipline_hours = {}

        for group_model in group_models:
            print(
                f"Загрузка группы: {group_model.name}, shift_number из БД: {group_model.shift_number}"
            )

            # Загружаем расписание пар для группы
            shift_pairs = {}
            pair_models = (
                session.query(GroupShiftPairModel)
                .filter_by(group_id=group_model.id)
                .all()
            )
            for pair_model in pair_models:
                pair_time = PairTime(
                    start=time.fromisoformat(pair_model.start_time),
                    end=time.fromisoformat(pair_model.end_time),
                    pair_type=pair_model.pair_type,
                )
                shift_pairs[pair_model.pair_number] = pair_time
                if pair_model.pair_number == 1:
                    print(
                        f"  Первая пара: {pair_model.start_time} - {pair_model.end_time}"
                    )

            data.groups_shift[group_model.name] = shift_pairs

            # Загружаем часы дисциплин
            discipline_models = (
                session.query(DisciplineHoursModel)
                .filter_by(group_id=group_model.id)
                .all()
            )
            if group_model.name not in data.discipline_hours:
                data.discipline_hours[group_model.name] = {}
            for disc_model in discipline_models:
                data.discipline_hours[group_model.name][disc_model.discipline_name] = (
                    disc_model.hours
                )

        # Загружаем временные интервалы смен
        shift_models = session.query(ShiftTimeModel).all()
        data.schedule_time_shift_1 = {}
        data.schedule_time_shift_2 = {}
        data.schedule_time_shift_3 = {}

        for shift_model in shift_models:
            pair_time = PairTime(
                start=time.fromisoformat(shift_model.start_time),
                end=time.fromisoformat(shift_model.end_time),
                pair_type=shift_model.pair_type,
            )

            if shift_model.shift_number == 1:
                data.schedule_time_shift_1[shift_model.pair_number] = pair_time
            elif shift_model.shift_number == 2:
                data.schedule_time_shift_2[shift_model.pair_number] = pair_time
            elif shift_model.shift_number == 3:
                data.schedule_time_shift_3[shift_model.pair_number] = pair_time

        logger.info(
            f"Данные успешно загружены: групп={len(data.discipline_hours)}, преподавателей={len(data.teachers)}, аудиторий={len(data.rooms)}"
        )
        return data

    except Exception as e:
        logger.exception(f"Ошибка при загрузке данных: {e}")
        raise
    finally:
        session.close()


# endregion


def save_data(data) -> None:
    """Сохранение данных с использованием SQLAlchemy"""
    logger.debug("Вызов save_data")
    save_data_sqlalchemy(data)


def load_data() -> Data:
    """Загрузка данных с использованием SQLAlchemy"""
    logger.debug("Вызов load_data")
    return load_data_sqlalchemy()


def check_exists_data() -> bool:
    """Проверка существования SQLite базы данных"""
    db_path = get_sqlite_db_path()
    return os.path.exists(db_path)


def resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def get_data_file_path():
    base_path = Path(os.path.expanduser("~")) / DB_PATH_NAME
    base_path.mkdir(parents=True, exist_ok=True)
    return base_path / DB_FILE


# region Conversion Functions


def convert_pair_time_to_schema(pair_time: PairTime) -> PairTimeSchema:
    """Конвертация PairTime в PairTimeSchema"""
    return PairTimeSchema(
        start=pair_time.start, end=pair_time.end, pair_type=pair_time.pair_type
    )


def convert_pair_to_schema(pair: Pair) -> PairSchema:
    """Конвертация Pair в PairSchema"""
    return PairSchema(
        date=pair.date,
        day=pair.day,
        number=pair.number,
        pair_time=convert_pair_time_to_schema(pair.pair_time),
        pair_type=pair.pair_type,
        group=pair.group,
        discipline=pair.discipline,
        teacher=pair.teacher,
        classroom=pair.classroom,
    )


def convert_teacher_to_schema(teacher: Teacher) -> TeacherSchema:
    """Конвертация Teacher в TeacherSchema"""
    return TeacherSchema(
        name=teacher.name, disciplines=teacher.disciplines, groups=teacher.groups
    )


def convert_teachers_schedule_to_schema(
    schedule: TeachersSchedule,
) -> TeachersScheduleSchema:
    """Конвертация TeachersSchedule в TeachersScheduleSchema"""
    return TeachersScheduleSchema(
        Понедельник=schedule.schedule_for_days["Понедельник"],
        Вторник=schedule.schedule_for_days["Вторник"],
        Среда=schedule.schedule_for_days["Среда"],
        Четверг=schedule.schedule_for_days["Четверг"],
        Пятница=schedule.schedule_for_days["Пятница"],
        Суббота=schedule.schedule_for_days["Суббота"],
        Воскресенье=schedule.schedule_for_days["Воскресенье"],
    )


def convert_room_schedule_to_schema(schedule: RoomSchedule) -> RoomScheduleSchema:
    """Конвертация RoomSchedule в RoomScheduleSchema"""
    return RoomScheduleSchema(
        Понедельник=schedule.schedule_for_days["Понедельник"],
        Вторник=schedule.schedule_for_days["Вторник"],
        Среда=schedule.schedule_for_days["Среда"],
        Четверг=schedule.schedule_for_days["Четверг"],
        Пятница=schedule.schedule_for_days["Пятница"],
        Суббота=schedule.schedule_for_days["Суббота"],
        Воскресенье=schedule.schedule_for_days["Воскресенье"],
    )


def convert_room_to_schema(room: Room) -> RoomSchema:
    """Конвертация Room в RoomSchema"""
    return RoomSchema(is_online=room.is_online)


def convert_data_to_schema(data: Data) -> DataSchema:
    """Конвертация Data в DataSchema"""
    # Конвертируем schedule_time_shift
    schedule_time_shift_1 = {
        num: convert_pair_time_to_schema(pair_time)
        for num, pair_time in data.schedule_time_shift_1.items()
    }
    schedule_time_shift_2 = {
        num: convert_pair_time_to_schema(pair_time)
        for num, pair_time in data.schedule_time_shift_2.items()
    }
    schedule_time_shift_3 = {
        num: convert_pair_time_to_schema(pair_time)
        for num, pair_time in data.schedule_time_shift_3.items()
    }

    # Конвертируем groups_shift
    groups_shift = {}
    for group, shift in data.groups_shift.items():
        groups_shift[group] = {
            num: convert_pair_time_to_schema(pair_time)
            for num, pair_time in shift.items()
        }

    # Конвертируем teachers
    teachers = {}
    for teacher_name, teacher_list in data.teachers.items():
        teachers[teacher_name] = [
            convert_teacher_to_schema(teacher) for teacher in teacher_list
        ]

    # Конвертируем teachers_work_hours
    teachers_work_hours = {
        teacher_name: convert_teachers_schedule_to_schema(schedule)
        for teacher_name, schedule in data.teachers_work_hours.items()
    }

    # Конвертируем rooms
    rooms = {
        room_name: convert_room_to_schema(room)
        for room_name, room in data.rooms.items()
    }

    # Конвертируем rooms_availability_hours
    rooms_availability_hours = {
        room_name: convert_room_schedule_to_schema(schedule)
        for room_name, schedule in data.rooms_availability_hours.items()
    }

    return DataSchema(
        counter=data.counter,
        days=data.days,
        teachers_schedule_time=data.teachers_schedule_time,
        schedule_time_shift_1=schedule_time_shift_1,
        schedule_time_shift_2=schedule_time_shift_2,
        schedule_time_shift_3=schedule_time_shift_3,
        groups_shift=groups_shift,
        discipline_hours=data.discipline_hours,
        teachers=teachers,
        teachers_work_hours=teachers_work_hours,
        rooms=rooms,
        rooms_availability_hours=rooms_availability_hours,
    )


def load_and_convert_data() -> DataSchema:
    """Загрузка данных из файла и конвертация в DataSchema"""
    data = load_data()
    return convert_data_to_schema(data)


# endregion


# endregion
