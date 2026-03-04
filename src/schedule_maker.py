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
from dataclasses import dataclass

from config.logger import get_logger
from config.constants import RoomPrefix, PairType, DAYS
from src import db
from src.schemas import (
    DataSchema,
    PairSchema,
    PairTimeSchema,
    RoomScheduleSchema,
    TeacherSchema,
)

logger = get_logger("schedule_maker")


class ScheduleError(ValueError):
    def __init__(self, message: str, discipline=None, group=None, hours=None):
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
    logger.debug("Вывод расписания:")
    for group in schedule:
        logger.debug(f"Группа: {group}")
        for pair in schedule[group]:
            logger.debug(f"  {pair}")


def sorted_pairs(pairs: dict[str, list[PairSchema]]) -> dict[str, list[PairSchema]]:
    for group in pairs:
        pairs[group] = sorted(pairs[group], key=lambda p: DAYS.index(p.day))
    return pairs


def get_schedule_for(
    key: str, pairs: dict[str, list[PairSchema]], value: str
) -> dict[str, list[PairSchema]]:
    pairs_list = copy.deepcopy(pairs)
    for group in pairs_list:
        match key:
            case "group":
                pairs_list[group] = list(
                    filter(lambda pair: pair.group == value, pairs_list[group])
                )
            case "discipline":
                pairs_list[group] = list(
                    filter(lambda pair: pair.discipline == value, pairs_list[group])
                )
            case "teacher":
                pairs_list[group] = list(
                    filter(lambda pair: pair.teacher == value, pairs_list[group])
                )
            case "classroom":
                pairs_list[group] = list(
                    filter(lambda pair: pair.classroom == value, pairs_list[group])
                )
            case "pair_type":
                pairs_list[group] = list(
                    filter(lambda pair: pair.pair_type == value, pairs_list[group])
                )
            case "day":
                pairs_list[group] = list(
                    filter(lambda pair: pair.day == value, pairs_list[group])
                )
            case "number":
                pairs_list[group] = list(
                    filter(lambda pair: pair.number == value, pairs_list[group])
                )
            case "pair_time":
                pairs_list[group] = list(
                    filter(lambda pair: pair.pair_time == value, pairs_list[group])
                )
            case "date":
                pairs_list[group] = list(
                    filter(lambda pair: pair.date == value, pairs_list[group])
                )
            case _:
                msg = f"Неизвестный ключ '{key}'"
                raise ValueError(msg)
    return pairs_list


def print_errors(errors_list: list[ScheduleError]) -> None:
    logger.warning(f"Ошибки расписания ({len(errors_list)}):")
    for error in errors_list:
        logger.warning(
            f"Невозможно поставить пару для группы {error.group}, для дисциплины {error.discipline}, оставшиеся часы: {error.hours}"
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
    return full_schedule, errors  # Возвращаем полное расписание


def distribute_classrooms(
    raw_sch: dict, data: DataSchema
) -> dict[str, list[PairSchema]]:
    raw_sch = raw_sch.copy()
    available_rooms: dict[str, RoomScheduleSchema] = data.rooms_availability_hours
    for list_of_pairs in raw_sch.values():
        for pair in list_of_pairs:
            if pair.classroom is not None:
                continue
            if pair.pair_type == PairType.ONLINE.value:  # Если онлайн
                _available_rooms_list = [
                    (room, sc)
                    for room, sc in available_rooms.items()
                    if room.startswith(RoomPrefix.DIGITAL.value)
                ]
            else:
                _available_rooms_list = [
                    (room, sc)
                    for room, sc in available_rooms.items()
                    if room.startswith(RoomPrefix.CLASSROOM.value)
                ]
            for room, room_schedule in _available_rooms_list:
                day_schedule = room_schedule.schedule_for_days[pair.day]
                if not day_schedule[room_schedule.get_pair_number(pair.pair_time) - 1]:
                    # Если пара свободна
                    pair.classroom = room
                    day_schedule[room_schedule.get_pair_number(pair.pair_time) - 1] = (
                        True
                    )
                    break
    return raw_sch


def make_full_schedule(data: DataSchema) -> Schedule:
    import time

    start_time = time.time()
    logger.info("Начало генерации полного расписания")
    logger.debug(
        f"Входные данные: групп={len(data.discipline_hours)}, преподавателей={len(data.teachers)}"
    )

    data = copy.deepcopy(data)
    full_schedule, errors = distribute_pairs(data)
    logger.info(f"Распределение пар завершено, ошибок: {len(errors)}")

    full_schedule = distribute_classrooms(full_schedule, data)
    logger.info("Распределение аудиторий завершено")

    full_schedule = sorted_pairs(full_schedule)
    elapsed_time = time.time() - start_time
    logger.info(
        f"Генерация расписания завершена, групп: {len(full_schedule)}, время: {elapsed_time:.2f}с"
    )
    return Schedule(pairs=full_schedule, errors=errors, remaining_data=data)


if __name__ == "__main__":
    d = db.load_and_convert_data()
    sch = make_full_schedule(d)
    print_schedule(sch.pairs)
    print_errors(sch.errors)
