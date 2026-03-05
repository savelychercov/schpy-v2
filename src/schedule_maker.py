"""
Модуль для автоматизированного составления расписания учебных занятий.

Функциональность:
- Распределение учебных пар по группам на основе доступных часов, преподавателей и их рабочих ограничений.
- Подбор свободных временных слотов с учётом смены группы и занятости преподавателей.
- Формирование ошибок расписания, если невозможно разместить пару.
- Распределение доступных аудиторий по занятиям (офлайн/онлайн).
- Сортировка и итоговая сборка полного расписания.

Основные компоненты:
- Schedule — dataclass, содержащий итоговое расписание, ошибки и оставшиеся данные.
- ScheduleError — исключение, возникающее при невозможности поставить пару.
- distribute_pairs() — формирует расписание по дисциплинам и преподавателям.
- distribute_classrooms() — распределяет аудитории для уже составленных пар.
- choose_a_pair_time() — ищет подходящее время для конкретной пары.
- get_schedule_for() — фильтрует расписание по заданному параметру.
- print_schedule() и print_errors() — вспомогательные функции для вывода результатов.
- make_full_schedule() — запускает полный цикл составления расписания.

Модуль использует структуры данных из модуля db, такие, как Pair, Teacher, RoomSchedule и Data.
Предназначен для автоматизации создания недельного расписания и анализа возможных конфликтов.
"""

import copy
import time
from dataclasses import dataclass

from config.constants import DAYS, PairType, RoomPrefix
from config.logger import get_logger
from config.settings import ENABLE_SCHEDULE_LOGS
from src import db
from src.db import PairTime, RoomSchedule
from src.schemas import (
    DataSchema,
    PairSchema,
    PairTimeSchema,
    RoomScheduleSchema,
    TeacherSchema,
)

logger = get_logger("schedule_maker")


class ScheduleError(ValueError):
    def __init__(
        self,
        message: str,
        discipline: str | None = None,
        group: str | None = None,
        hours: int | None = None,
    ):
        super().__init__(message)
        self.discipline = discipline
        self.group = group
        self.hours = hours


@dataclass
class Schedule:
    pairs: dict[str, list[PairSchema]]
    errors: list[ScheduleError]
    remaining_data: DataSchema


def print_schedule(schedule: dict[str, list[PairSchema]]) -> None:
    if ENABLE_SCHEDULE_LOGS:
        logger.debug("Printing schedule:")
        for group, group_pairs in schedule.items():
            logger.debug("Group: %s", group)
            for pair in group_pairs:
                logger.debug("  %s", pair)


def sorted_pairs(pairs: dict[str, list[PairSchema]]) -> dict[str, list[PairSchema]]:
    for group, group_pairs in pairs.items():
        pairs[group] = sorted(group_pairs, key=lambda p: DAYS.index(p.day))
    return pairs


def _filter_pairs_by_key(
    pairs: list[PairSchema], key: str, value: str
) -> list[PairSchema]:
    """Filter pairs based on the given key and value."""
    filter_map = {
        "group": lambda pair: pair.group == value,
        "discipline": lambda pair: pair.discipline == value,
        "teacher": lambda pair: pair.teacher == value,
        "classroom": lambda pair: pair.classroom == value,
        "pair_type": lambda pair: pair.pair_type == value,
        "day": lambda pair: pair.day == value,
        "number": lambda pair: pair.number == value,
        "pair_time": lambda pair: pair.pair_time == value,
        "date": lambda pair: pair.date == value,
    }

    filter_func = filter_map.get(key)
    if filter_func is None:
        msg = f"Неизвестный ключ '{key}'"
        raise ValueError(msg)

    return list(filter(filter_func, pairs))


def get_schedule_for(
    key: str, pairs: dict[str, list[PairSchema]], value: str
) -> dict[str, list[PairSchema]]:
    pairs_list = copy.deepcopy(pairs)
    for group in pairs_list:
        pairs_list[group] = _filter_pairs_by_key(pairs_list[group], key, value)
    return pairs_list


def print_errors(errors_list: list[ScheduleError]) -> None:
    if ENABLE_SCHEDULE_LOGS:
        logger.warning("Schedule errors (%d):", len(errors_list))
        for error in errors_list:
            logger.warning(
                "Cannot place pair for group %s, discipline %s, remaining hours: %d",
                error.group,
                error.discipline,
                error.hours,
            )


def choose_a_pair_time(
    existing_pairs: list[PairSchema],
    discipline: str,
    group: str,
    teacher: TeacherSchema,
    data: DataSchema,
) -> PairSchema:
    shift = data.groups_shift[group]
    teachers_schedule = data.teachers_work_hours[teacher.name]
    # Ищем первое свободное время для дисциплины
    for day in DAYS:
        for number, pair_time in shift.items():
            if number in [pair.number for pair in existing_pairs if pair.day == day]:
                continue
            try:
                teachers_schedule.choose_pair(day, pair_time)
            except ValueError:
                continue
            # Создаем объект пары
            pair_time_schema = PairTimeSchema(
                start=pair_time.start, end=pair_time.end, pair_type=pair_time.pair_type
            )
            return PairSchema(
                date="2024-XX-XX",  # (Можно изменить на даты текущей недели после составления)
                day=day,
                number=number,
                pair_time=pair_time_schema,
                pair_type=pair_time.pair_type,
                group=group,
                discipline=discipline,
                teacher=teacher.name,
                classroom=None,
            )
    msg = "Невозможно найти свободное время"
    raise ScheduleError(msg, discipline=discipline, group=group)


def distribute_pairs(
    data: DataSchema,
) -> tuple[dict[str, list[PairSchema]], list[ScheduleError]]:
    full_schedule = {}  # Словарь для хранения расписания по группам
    errors = []
    remaining_hours = data.discipline_hours

    for group in data.groups_shift:
        full_schedule[group] = []  # Инициализируем список для каждой группы
        # Итерируемся по дисциплинам
        if group not in remaining_hours:
            continue
        for discipline in remaining_hours[
            group
        ]:  # M получаем недельные часы по дисциплине.
            # Ищем подходящего преподавателя для дисциплины
            if remaining_hours[group][discipline] == 0:  # M
                continue
            for preset in data.teachers.values():
                for teacher in preset:
                    if not (
                        discipline in teacher.disciplines and group in teacher.groups
                    ):
                        continue
                    try:
                        while remaining_hours[group][discipline] > 0:
                            pair = choose_a_pair_time(
                                full_schedule[group], discipline, group, teacher, data
                            )
                            full_schedule[group].append(
                                pair
                            )  # Добавляем пару в расписание
                            remaining_hours[group][discipline] -= 2
                    except ScheduleError as e:
                        e.hours = remaining_hours[group][discipline]
                        errors.append(e)
                    break  # Прерываем поиск после нахождения первого подходящего преподавателя
    return (
        full_schedule,
        errors,
        remaining_hours,
    )  # Возвращаем полное расписание, ошибки и оставшиеся часы


def distribute_classrooms(  # noqa: C901, PLR0912
    raw_sch: dict, data: DataSchema
) -> dict[str, list[PairSchema]]:
    available_rooms: dict[str, RoomScheduleSchema] = data.rooms_availability_hours
    if ENABLE_SCHEDULE_LOGS:
        logger.info(
            "Starting classroom distribution, available rooms: %d", len(available_rooms)
        )

    # Создаем временные рабочие копии расписаний
    working_rooms = {}
    for room_name, room_schedule in available_rooms.items():
        working_rooms[room_name] = {
            day: list(schedule)  # копируем списки
            for day, schedule in room_schedule.schedule_for_days.items()
        }
        if ENABLE_SCHEDULE_LOGS:
            logger.debug(
                "Room %s initial state: %s",
                room_name,
                {
                    day: working_rooms[room_name][day][:3]
                    for day in ["Понедельник", "Вторник", "Среда"]
                },
            )

    pairs_without_classroom = 0
    pairs_with_classroom = 0

    for group, list_of_pairs in raw_sch.items():
        for pair in list_of_pairs:
            if pair.classroom is not None:
                pairs_with_classroom += 1
                continue
            pairs_without_classroom += 1

            # Определяем тип аудитории
            if pair.pair_type == PairType.ONLINE.value:
                prefix = RoomPrefix.DIGITAL.value
            else:
                prefix = RoomPrefix.CLASSROOM.value

            # Конвертируем время в номер пары
            pair_time_db = PairTime(
                pair.pair_time.start, pair.pair_time.end, pair.pair_time.pair_type
            )
            pair_number = RoomSchedule.get_pair_number(pair_time_db)

            if pair_number is None:
                if ENABLE_SCHEDULE_LOGS:
                    logger.warning(
                        "Could not determine pair number for %s - %s at %s",
                        group,
                        pair.discipline,
                        pair.day,
                    )
                continue

            # Ищем свободную аудиторию
            assigned = False
            for room_name, room_schedule_dict in working_rooms.items():
                if not room_name.startswith(prefix):
                    continue

                day_schedule = room_schedule_dict.get(pair.day)
                if day_schedule is None:
                    continue

                # Проверяем доступность
                if pair_number <= len(day_schedule) and day_schedule[pair_number - 1]:
                    # Назначаем аудиторию
                    pair.classroom = room_name
                    day_schedule[pair_number - 1] = False
                    assigned = True
                    pairs_with_classroom += 1
                    pairs_without_classroom -= 1  # Уменьшаем счетчик пар без аудитории
                    if ENABLE_SCHEDULE_LOGS:
                        logger.debug(
                            "Assigned room %s to %s - %s at %s pair %d",
                            room_name,
                            group,
                            pair.discipline,
                            pair.day,
                            pair_number,
                        )
                    break

            if not assigned and ENABLE_SCHEDULE_LOGS:
                # Проверим, какие аудитории были доступны
                available_at_time = []
                for room_name, room_schedule_dict in working_rooms.items():
                    if not room_name.startswith(prefix):
                        continue
                    day_schedule = room_schedule_dict.get(pair.day)
                    if day_schedule and pair_number <= len(day_schedule):
                        if day_schedule[pair_number - 1]:
                            available_at_time.append(room_name)
                logger.warning(
                    "No room for %s - %s at %s pair %d. Available rooms at that time: %s",
                    group,
                    pair.discipline,
                    pair.day,
                    pair_number,
                    available_at_time,
                )

    if ENABLE_SCHEDULE_LOGS:
        # Покажем финальное состояние аудиторий
        for room_name, room_schedule_dict in working_rooms.items():
            logger.debug(
                "Room %s final state: %s",
                room_name,
                {
                    day: room_schedule_dict[day][:3]
                    for day in ["Понедельник", "Вторник", "Среда"]
                },
            )
        logger.info(
            "Classroom distribution completed. Pairs processed: %d, with classrooms: %d, without: %d",
            pairs_without_classroom + pairs_with_classroom,
            pairs_with_classroom,
            pairs_without_classroom,
        )

    return raw_sch


def make_full_schedule(data: DataSchema) -> Schedule:
    start_time = time.time()
    if ENABLE_SCHEDULE_LOGS:
        logger.info("Starting full schedule generation")

    working_data = copy.deepcopy(data)
    full_schedule, errors, remaining_hours = distribute_pairs(working_data)
    full_schedule = distribute_classrooms(full_schedule, working_data)
    full_schedule = sorted_pairs(full_schedule)

    # Обновляем remaining_data с вычтенными часами
    remaining_data = copy.deepcopy(data)
    remaining_data.discipline_hours = remaining_hours

    elapsed_time = time.time() - start_time
    if ENABLE_SCHEDULE_LOGS:
        total_pairs = sum(len(pairs) for pairs in full_schedule.values())
        pairs_with_rooms = sum(
            1
            for pairs in full_schedule.values()
            for pair in pairs
            if pair.classroom is not None
        )
        logger.info(
            "Schedule generation completed, total pairs: %d, with rooms: %d, time: %.2fs",
            total_pairs,
            pairs_with_rooms,
            elapsed_time,
        )

    return Schedule(pairs=full_schedule, errors=errors, remaining_data=remaining_data)


if __name__ == "__main__":
    d = db.load_and_convert_data()
    sch = make_full_schedule(d)
    print_schedule(sch.pairs)
    print_errors(sch.errors)
