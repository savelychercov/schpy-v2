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

import os
import pickle
import sys
from abc import ABC, abstractmethod
from datetime import time, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, Text, 
    ForeignKey, LargeBinary
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.sqlite import JSON
import json

from src.schemas import (
    PairTimeSchema,
    PairSchema,
    TeacherSchema,
    TeachersScheduleSchema,
    RoomScheduleSchema,
    RoomSchema,
    DataSchema
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
                self.schedule_for_days[day] = [False] * 6
            while len(self.schedule_for_days[day]) < 6:
                self.schedule_for_days[day].append(False)

    @staticmethod
    def get_pair_number(pair_time: PairTime) -> int | None:
        # Get number from teachers_schedule_time
        for number, (start, end) in teachers_schedule_time.items():
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
            raise ValueError(f"Невозможно выбрать время '{pair_time}'")
        if not self.schedule_for_days[day][pair_number - 1]:
            raise ValueError(f"Время '{pair_time}' занято или недоступно")
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
                self.schedule_for_days[day] = [False] * 6
            while len(self.schedule_for_days[day]) < 6:
                self.schedule_for_days[day].append(False)

    @staticmethod
    def get_pair_number(pair_time: PairTime) -> int | None:
        for number, (start, end) in teachers_schedule_time.items():
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


offline_str = "Офлайн"
online_str = "Онлайн"


db_file = "db.pickle"
db_path_name = "SchPyPickleData"

days = (
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
)
workweek_days = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница")

# CONST
teachers_schedule_time = {
    1: (time(8, 0), time(9, 30)),  # first pair for 1 shift, online for 2 shift
    2: (time(9, 40), time(11, 10)),  # second pair for 1 shift
    3: (time(11, 30), time(13, 0)),  # first pair for 2 shift, online for 3 shift
    4: (time(13, 10), time(14, 40)),  # second pair for 2 shift
    5: (time(15, 0), time(16, 30)),  # first pair for 3 shift
    6: (time(16, 40), time(18, 10)),  # second pair for 3 shift, online for 1 shift
}

# endregion


# region Data


class Data(ABC):
    @abstractmethod
    def __init__(self):
        raise NotImplementedError

    counter: int
    days: list = days
    teachers_schedule_time: dict = teachers_schedule_time
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
        self.days = days
        self.teachers_schedule_time = teachers_schedule_time
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

        self.days = days

        self.teachers_schedule_time = teachers_schedule_time

        self.schedule_time_shift_1 = {  # time schedule for first shift
            1: PairTime(time(8, 0), time(9, 30), offline_str),
            2: PairTime(time(9, 40), time(11, 10), offline_str),
            3: PairTime(time(16, 40), time(17, 40), online_str),
        }

        self.schedule_time_shift_2 = {  # time schedule for second shift
            1: PairTime(time(8, 0), time(9, 0), online_str),
            2: PairTime(time(11, 30), time(13, 0), offline_str),
            3: PairTime(time(13, 10), time(14, 40), offline_str),
        }

        self.schedule_time_shift_3 = {  # time schedule for third shift
            1: PairTime(time(11, 50), time(12, 50), online_str),
            2: PairTime(time(15, 0), time(16, 30), offline_str),
            3: PairTime(time(16, 40), time(18, 10), offline_str),
        }

        self.groups_shift = {
            "П9024": self.schedule_time_shift_1,
            "П9022": self.schedule_time_shift_2,
            "П9021": self.schedule_time_shift_3,
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
    __tablename__ = 'teachers'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    disciplines = Column(Text, nullable=False)  # JSON сериализация set
    groups = Column(Text, nullable=False)        # JSON сериализация set
    
    # Связь с расписанием
    schedules = relationship("TeacherScheduleModel", back_populates="teacher", cascade="all, delete-orphan")
    
    def to_teacher(self):
        """Конвертация в объект Teacher"""
        import json
        return Teacher(
            name=self.name,
            disciplines=set(json.loads(self.disciplines)),
            groups=set(json.loads(self.groups))
        )

class TeacherScheduleModel(Base):
    __tablename__ = 'teachers_schedule'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    teacher_name = Column(String, ForeignKey('teachers.name'), nullable=False)
    day = Column(String, nullable=False)
    schedule = Column(Text, nullable=False)  # JSON сериализация list[bool]
    
    # Связь с преподавателем
    teacher = relationship("TeacherModel", back_populates="schedules")

class RoomModel(Base):
    __tablename__ = 'rooms'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    is_online = Column(Boolean, default=False)
    
    # Связь с расписанием
    schedules = relationship("RoomScheduleModel", back_populates="room", cascade="all, delete-orphan")

class RoomScheduleModel(Base):
    __tablename__ = 'rooms_schedule'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    room_name = Column(String, ForeignKey('rooms.name'), nullable=False)
    day = Column(String, nullable=False)
    schedule = Column(Text, nullable=False)  # JSON сериализация list[bool]
    
    # Связь с аудиторией
    room = relationship("RoomModel", back_populates="schedules")

class MainDataModel(Base):
    __tablename__ = 'main_data'
    
    id = Column(Integer, primary_key=True, default=1)
    counter = Column(Integer, default=1)

class DisciplineHoursModel(Base):
    __tablename__ = 'discipline_hours'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_name = Column(String, nullable=False)
    discipline_name = Column(String, nullable=False)
    hours = Column(Integer, nullable=False)

class GroupsShiftModel(Base):
    __tablename__ = 'groups_shift'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_name = Column(String, nullable=False)
    pair_number = Column(Integer, nullable=False)
    # Сохраняем PairTime как JSON
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    pair_type = Column(String, nullable=False)

class ScheduleTimeShiftModel(Base):
    __tablename__ = 'schedule_time_shift'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    shift_number = Column(Integer, nullable=False)  # 1, 2, or 3
    pair_number = Column(Integer, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    pair_type = Column(String, nullable=False)

# endregion


# region SQLAlchemy Database Functions

def get_sqlite_db_path() -> str:
    """Получение пути к файлу SQLite базы данных"""
    data_path = get_data_file_path()
    if isinstance(data_path, Path):
        db_path = data_path.with_suffix('.db')
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
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
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


def save_data_sqlalchemy(data) -> None:
    """Сохранение данных с использованием SQLAlchemy + Pydantic схемы"""
    print("Сохранение данных в SQLAlchemy базу")
    
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
        
        # Очищаем существующие данные
        session.query(TeacherScheduleModel).delete()
        session.query(TeacherModel).delete()
        session.query(RoomScheduleModel).delete()
        session.query(RoomModel).delete()
        session.query(DisciplineHoursModel).delete()
        session.query(GroupsShiftModel).delete()
        session.query(ScheduleTimeShiftModel).delete()
        
        # Сохраняем преподавателей через Pydantic схему
        for teacher_name, teacher_list in data.teachers.items():
            for teacher in teacher_list:
                # Конвертируем в Pydantic схему
                teacher_schema = TeacherSchema(
                    name=teacher.name,
                    disciplines=list(teacher.disciplines),
                    groups=list(teacher.groups)
                )
                
                teacher_model = TeacherModel(
                    name=teacher_schema.name,
                    disciplines=json.dumps(list(teacher_schema.disciplines), ensure_ascii=False),
                    groups=json.dumps(list(teacher_schema.groups), ensure_ascii=False)
                )
                session.add(teacher_model)
                
                # Сохраняем расписание преподавателя через Pydantic схему
                if teacher.name in data.teachers_work_hours:
                    schedule = data.teachers_work_hours[teacher.name]
                    
                    # Создаем полную схему расписания
                    schedule_dict = {}
                    for day in ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']:
                        schedule_dict[day] = schedule.schedule_for_days.get(day, [False] * 6)
                    
                    schedule_schema = TeachersScheduleSchema(**schedule_dict)
                    
                    # Сохраняем каждый день отдельно
                    for day, schedule_list in schedule_dict.items():
                        schedule_model = TeacherScheduleModel(
                            teacher_name=teacher.name,
                            day=day,
                            schedule=json.dumps(schedule_list, ensure_ascii=False)
                        )
                        session.add(schedule_model)
        
        # Сохраняем аудитории через Pydantic схему
        for room_name, room_schedule in data.rooms_availability_hours.items():
            is_online = room_name.startswith("Д")  # Д - онлайн аудитории
            
            room_schema = RoomSchema(is_online=is_online)
            
            room_model = RoomModel(
                name=room_name,
                is_online=room_schema.is_online
            )
            session.add(room_model)
            
            # Сохраняем расписание аудитории через Pydantic схему
            schedule_dict = {}
            for day in ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']:
                schedule_dict[day] = room_schedule.schedule_for_days.get(day, [False] * 6)
            
            schedule_schema = RoomScheduleSchema(**schedule_dict)
            
            # Сохраняем каждый день отдельно
            for day, schedule_list in schedule_dict.items():
                schedule_model = RoomScheduleModel(
                    room_name=room_name,
                    day=day,
                    schedule=json.dumps(schedule_list, ensure_ascii=False)
                )
                session.add(schedule_model)
        
        # Сохраняем discipline_hours
        if hasattr(data, 'discipline_hours') and data.discipline_hours:
            for group_name, disciplines in data.discipline_hours.items():
                for discipline_name, hours in disciplines.items():
                    discipline_model = DisciplineHoursModel(
                        group_name=group_name,
                        discipline_name=discipline_name,
                        hours=hours
                    )
                    session.add(discipline_model)
        
        # Сохраняем groups_shift
        if hasattr(data, 'groups_shift') and data.groups_shift:
            for group_name, shift_dict in data.groups_shift.items():
                for pair_number, pair_time in shift_dict.items():
                    shift_model = GroupsShiftModel(
                        group_name=group_name,
                        pair_number=pair_number,
                        start_time=pair_time.start.strftime('%H:%M:%S'),
                        end_time=pair_time.end.strftime('%H:%M:%S'),
                        pair_type=pair_time.pair_type
                    )
                    session.add(shift_model)
        
        # Сохраняем schedule_time_shift
        for shift_name, shift_dict in [('schedule_time_shift_1', data.schedule_time_shift_1),
                                       ('schedule_time_shift_2', data.schedule_time_shift_2),
                                       ('schedule_time_shift_3', data.schedule_time_shift_3)]:
            if hasattr(data, shift_name) and shift_dict:
                shift_number = shift_name.split('_')[-1]
                for pair_number, pair_time in shift_dict.items():
                    time_shift_model = ScheduleTimeShiftModel(
                        shift_number=int(shift_number),
                        pair_number=pair_number,
                        start_time=pair_time.start.strftime('%H:%M:%S'),
                        end_time=pair_time.end.strftime('%H:%M:%S'),
                        pair_type=pair_time.pair_type
                    )
                    session.add(time_shift_model)
        
        session.commit()
        print("Данные успешно сохранены")
        
    except Exception as e:
        session.rollback()
        print(f"Ошибка при сохранении данных: {e}")
        raise
    finally:
        session.close()


def load_data_sqlalchemy() -> Data:
    """Загрузка данных с использованием SQLAlchemy + Pydantic схемы"""
    print("Загрузка данных из SQLAlchemy базы")
    
    if SessionLocal is None:
        init_db()
    
    session = get_db_session()
    try:
        # Проверяем, есть ли данные
        teacher_count = session.query(TeacherModel).count()
        if teacher_count == 0:
            print("База данных пуста, создаем пример данных")
            session.close()
            example_data = ExampleData()
            save_data_sqlalchemy(example_data)
            return example_data
        
        # Создаем объект данных
        data = EmptyData()
        
        # Загружаем счетчик
        main_data = session.query(MainDataModel).filter_by(id=1).first()
        data.counter = main_data.counter if main_data else 1
        
        # Загружаем discipline_hours
        discipline_models = session.query(DisciplineHoursModel).all()
        data.discipline_hours = {}
        for discipline_model in discipline_models:
            if discipline_model.group_name not in data.discipline_hours:
                data.discipline_hours[discipline_model.group_name] = {}
            data.discipline_hours[discipline_model.group_name][discipline_model.discipline_name] = discipline_model.hours
        
        # Загружаем преподавателей через Pydantic схемы
        teacher_models = session.query(TeacherModel).all()
        data.teachers = {}
        data.teachers_work_hours = {}
        
        for teacher_model in teacher_models:
            # Конвертируем в Pydantic схему для валидации
            teacher_schema = TeacherSchema(
                name=teacher_model.name,
                disciplines=json.loads(teacher_model.disciplines),
                groups=json.loads(teacher_model.groups)
            )
            
            teacher = Teacher(
                name=teacher_schema.name,
                disciplines=set(teacher_schema.disciplines),
                groups=set(teacher_schema.groups)
            )
            
            # Восстанавливаем структуру словаря
            if teacher.name not in data.teachers:
                data.teachers[teacher.name] = []
            data.teachers[teacher.name].append(teacher)
            
            # Создаем расписание преподавателя
            if teacher.name not in data.teachers_work_hours:
                teachers_schedule = TeachersSchedule()
                data.teachers_work_hours[teacher.name] = teachers_schedule
        
        # Загружаем расписание преподавателей через Pydantic схемы
        schedule_models = session.query(TeacherScheduleModel).all()
        
        # Группируем расписание по преподавателям
        teacher_schedules = {}
        for schedule_model in schedule_models:
            if schedule_model.teacher_name not in teacher_schedules:
                teacher_schedules[schedule_model.teacher_name] = {}
            teacher_schedules[schedule_model.teacher_name][schedule_model.day] = json.loads(schedule_model.schedule)
        
        # Восстанавливаем расписание через Pydantic схемы
        for teacher_name, schedule_dict in teacher_schedules.items():
            if teacher_name in data.teachers_work_hours:
                # Создаем полную схему для валидации
                full_schedule_dict = {}
                for day in ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']:
                    full_schedule_dict[day] = schedule_dict.get(day, [False] * 6)
                
                schedule_schema = TeachersScheduleSchema(**full_schedule_dict)
                
                # Сохраняем валидированные данные
                for day, schedule_list in full_schedule_dict.items():
                    data.teachers_work_hours[teacher_name].schedule_for_days[day] = schedule_list
        
        # Загружаем аудитории через Pydantic схемы
        room_models = session.query(RoomModel).all()
        data.rooms_availability_hours = {}
        data.rooms = {}
        
        for room_model in room_models:
            # Конвертируем в Pydantic схему для валидации
            room_schema = RoomSchema(is_online=room_model.is_online)
            
            room_schedule = RoomSchedule()
            data.rooms_availability_hours[room_model.name] = room_schedule
            
            # Создаем объект Room для data.rooms
            room = Room(is_online=room_model.is_online)
            data.rooms[room_model.name] = room
        
        # Загружаем расписание аудиторий через Pydantic схемы
        room_schedule_models = session.query(RoomScheduleModel).all()
        
        # Группируем расписание по аудиториям
        room_schedules = {}
        for schedule_model in room_schedule_models:
            if schedule_model.room_name not in room_schedules:
                room_schedules[schedule_model.room_name] = {}
            room_schedules[schedule_model.room_name][schedule_model.day] = json.loads(schedule_model.schedule)
        
        # Восстанавливаем расписание через Pydantic схемы
        for room_name, schedule_dict in room_schedules.items():
            if room_name in data.rooms_availability_hours:
                # Создаем полную схему для валидации
                full_schedule_dict = {}
                for day in ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']:
                    full_schedule_dict[day] = schedule_dict.get(day, [False] * 6)
                
                schedule_schema = RoomScheduleSchema(**full_schedule_dict)
                
                # Сохраняем валидированные данные
                for day, schedule_list in full_schedule_dict.items():
                    data.rooms_availability_hours[room_name].schedule_for_days[day] = schedule_list
        
        # Загружаем groups_shift
        group_shift_models = session.query(GroupsShiftModel).all()
        data.groups_shift = {}
        for shift_model in group_shift_models:
            if shift_model.group_name not in data.groups_shift:
                data.groups_shift[shift_model.group_name] = {}
            
            # Восстанавливаем PairTime
            from datetime import time
            pair_time = PairTime(
                start=time.fromisoformat(shift_model.start_time),
                end=time.fromisoformat(shift_model.end_time),
                pair_type=shift_model.pair_type
            )
            data.groups_shift[shift_model.group_name][shift_model.pair_number] = pair_time
        
        # Загружаем schedule_time_shift
        time_shift_models = session.query(ScheduleTimeShiftModel).all()
        for shift_model in time_shift_models:
            shift_name = f"schedule_time_shift_{shift_model.shift_number}"
            if not hasattr(data, shift_name):
                setattr(data, shift_name, {})
            
            # Восстанавливаем PairTime
            start_time = time.fromisoformat(shift_model.start_time)
            end_time = time.fromisoformat(shift_model.end_time)
            pair_time = PairTime(
                start=start_time,
                end=end_time,
                pair_type=shift_model.pair_type
            )
            getattr(data, shift_name)[shift_model.pair_number] = pair_time
        
        print("Данные успешно загружены")
        return data
        
    except Exception as e:
        print(f"Ошибка при загрузке данных: {e}")
        raise
    finally:
        session.close()


def save_data(data) -> None:
    """Сохранение данных с использованием SQLAlchemy"""
    save_data_sqlalchemy(data)


def load_data() -> Data:
    """Загрузка данных с использованием SQLAlchemy"""
    return load_data_sqlalchemy()


def check_exists_data() -> bool:
    """Проверка существования SQLite базы данных"""
    db_path = get_sqlite_db_path()
    return os.path.exists(db_path)


def resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def get_data_file_path():
    base_path = Path(os.path.expanduser("~")) / db_path_name
    base_path.mkdir(parents=True, exist_ok=True)
    return base_path / db_file


# region Conversion Functions


def convert_pair_time_to_schema(pair_time: PairTime) -> PairTimeSchema:
    """Конвертация PairTime в PairTimeSchema"""
    return PairTimeSchema(
        start=pair_time.start,
        end=pair_time.end,
        pair_type=pair_time.pair_type
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
        classroom=pair.classroom
    )


def convert_teacher_to_schema(teacher: Teacher) -> TeacherSchema:
    """Конвертация Teacher в TeacherSchema"""
    return TeacherSchema(
        name=teacher.name,
        disciplines=teacher.disciplines,
        groups=teacher.groups
    )


def convert_teachers_schedule_to_schema(schedule: TeachersSchedule) -> TeachersScheduleSchema:
    """Конвертация TeachersSchedule в TeachersScheduleSchema"""
    return TeachersScheduleSchema(
        Понедельник=schedule.schedule_for_days["Понедельник"],
        Вторник=schedule.schedule_for_days["Вторник"],
        Среда=schedule.schedule_for_days["Среда"],
        Четверг=schedule.schedule_for_days["Четверг"],
        Пятница=schedule.schedule_for_days["Пятница"],
        Суббота=schedule.schedule_for_days["Суббота"],
        Воскресенье=schedule.schedule_for_days["Воскресенье"]
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
        Воскресенье=schedule.schedule_for_days["Воскресенье"]
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
        rooms_availability_hours=rooms_availability_hours
    )


def load_and_convert_data() -> DataSchema:
    """Загрузка данных из файла и конвертация в DataSchema"""
    data = load_data()
    return convert_data_to_schema(data)


# endregion


# endregion
