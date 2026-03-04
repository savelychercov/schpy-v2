"""
Модуль содержит инструменты для стохастической оптимизации учебного расписания
путём многократного перемешивания входных данных и оценки качества полученного
расписания. Использует компоненты из модуля schedule_maker и структуры данных db.

Основные задачи модуля:

1. Перемешивание данных:
   - Случайная перестановка дней, преподавателей, аудиторий, рабочих часов и
     распределения часов дисциплин.
   - Генерация множества различных "посевов" данных для поиска более удачных
     комбинаций расписания.

2. Метрики оценки расписания:
   - Подсчёт непроставленных учебных часов.
   - Выявление разрывов в расписании преподавателя (пустые "окна").
   - Подсчёт пропусков в офлайн-парах в пределах дня.
   - Проверка перегрузки преподавателей сверх установленного лимита часов.
   - Итоговая рейтинговая оценка расписания на основе штрафов и коэффициентов.

3. Поиск лучшего расписания:
   - Генерация множества кандидатов расписаний через многократное перемешивание.
   - Сравнение расписаний по рейтингу.
   - Вывод лучшего результата, включая диагностические показатели качества.

4. Вспомогательные функции:
   - Случайное перемешивание словарей и кортежей.
   - Получение N лучших элементов по рейтингу.
   - Удобные вычислители метрик и статистики по расписанию.

Запуск как программы (__main__):
- Запрашивает количество итераций.
- В цикле создаёт случайные варианты данных, строит расписание и рассчитывает
  его рейтинг.
- Периодически выводит прогресс, время до завершения и текущий лучший результат.
- По окончании выводит лучшее найденное расписание и связанные метрики.

Модуль используется как инструмент оптимизации качества расписания путём
проб и ошибок, что позволяет приблизиться к варианту с минимальными конфликтами,
окнами, недораспределёнными часами и перегрузкой преподавателей.
"""

import copy
import random
import time

from config.logger import get_logger
from src import db, schedule_maker

logger = get_logger("best_of")

teachers_gaps_rating_modifier = 5
offline_pairs_gaps_rating_modifier = 13
owervorked_teachers_rating_modifier = 50
unissued_hours_rating_modifier = 3


max_working_hours_for_teacher = 36


# region Utils


def shuffled_dict(x: dict) -> dict:
    items = list(x.items())
    random.shuffle(items)
    return dict(items)


def shuffled_tuple(x: tuple) -> tuple:
    random.shuffle(copy.deepcopy(list(x)))
    return tuple(x)


def sub_percentage(x: float, percentage: float) -> float:
    # logger.debug(f"{x} - {percentage}% = {x - (x * percentage / 100)}")
    return max(0, x - (x * percentage / 100))


def shuffle_data(data_obj: db.Data) -> db.Data:
    data_obj = copy.deepcopy(data_obj)

    data_obj.days = shuffled_tuple(data_obj.days)
    data_obj.teachers = shuffled_dict(data_obj.teachers)
    data_obj.teachers_work_hours = shuffled_dict(data_obj.teachers_work_hours)
    data_obj.rooms = shuffled_dict(data_obj.rooms)
    data_obj.rooms_availability_hours = shuffled_dict(data_obj.rooms_availability_hours)
    for group in data_obj.discipline_hours:
        data_obj.discipline_hours[group] = shuffled_dict(
            data_obj.discipline_hours[group]
        )
    data_obj.discipline_hours = shuffled_dict(data_obj.discipline_hours)
    data_obj.groups_shift = shuffled_dict(data_obj.groups_shift)
    return data_obj


def get_top(seeds_rating_dict: dict, count: int) -> dict:
    seeds_rating_dict = {
        k: v for k, v in sorted(seeds_rating_dict.items(), key=lambda item: item[1])
    }
    if len(seeds_rating_dict) < count:
        return seeds_rating_dict
    return dict(list(seeds_rating_dict.items())[-count:][::-1])


# endregion


# region Schedule rating


def count_unissued_hours(remaining_data: db.Data) -> int:
    count = 0
    for group, discipline_hours in remaining_data.discipline_hours.items():
        for discipline, hours in discipline_hours.items():
            count += hours
    return count


def count_teachers_gaps(original_data: db.Data, remaining_data: db.Data) -> int:
    count = 0
    for teacher, teachers_schedule in original_data.teachers_work_hours.items():
        for day in teachers_schedule.schedule_for_days:
            chosen_pairs = []
            first = remaining_data.teachers_work_hours[teacher].schedule_for_days[day]
            second = teachers_schedule.schedule_for_days[day]
            for n, (b1, b2) in enumerate(zip(first, second)):
                if not b1 and b2:
                    chosen_pairs.append(n)
            if not chosen_pairs:
                continue
            for i in range(min(chosen_pairs), max(chosen_pairs) + 1):
                if i not in chosen_pairs:
                    count += 1
    return count


def count_offline_pairs_gaps(pairs: dict[str, list[db.Pair]], data_obj: db.Data) -> int:
    count = 0
    for group, list_of_pairs in pairs.items():
        offline_pair_numbers = [
            number
            for number, pair_time in data_obj.groups_shift[group].items()
            if pair_time.pair_type == db.offline_str
        ]
        for day in db.workweek_days:
            offline_pair_numbers_for_day = [
                pair.number
                for pair in list_of_pairs
                if pair.day == day and pair.number in offline_pair_numbers
            ]
            if len(offline_pair_numbers_for_day) != len(offline_pair_numbers):
                count += max(
                    0, len(offline_pair_numbers) - len(offline_pair_numbers_for_day)
                )
    return count


def count_overworked_teachers(pairs: dict[str, list[db.Pair]]) -> int:
    count_hours_for_teachers = {}
    for group, list_of_pairs in pairs.items():
        for pair in list_of_pairs:
            if pair.teacher not in count_hours_for_teachers:
                count_hours_for_teachers[pair.teacher] = 0
            count_hours_for_teachers[pair.teacher] += 2
    count = 0
    for teacher, count_hours in count_hours_for_teachers.items():
        if count_hours > max_working_hours_for_teacher:
            count += 1
    return count


def rate_schedule(
    schedule: dict[str, list[db.Pair]], original_data: db.Data, remaining_data: db.Data
) -> float:
    rate = 100
    teachers_gaps_count = count_teachers_gaps(original_data, remaining_data)
    rate = sub_percentage(rate, teachers_gaps_count * teachers_gaps_rating_modifier)
    # logger.debug(f"after teachers_gaps_count {rate}")

    offline_pairs_gaps = count_offline_pairs_gaps(schedule, original_data)
    rate = sub_percentage(rate, offline_pairs_gaps * offline_pairs_gaps_rating_modifier)
    # logger.debug(f"after offline_pairs_gaps {rate}")

    overworked_teachers = count_overworked_teachers(schedule)
    rate = sub_percentage(
        rate, overworked_teachers * owervorked_teachers_rating_modifier
    )
    # logger.debug(f"after overworked_teachers {rate}")

    unissued_hours = count_unissued_hours(remaining_data)
    rate = sub_percentage(rate, unissued_hours * unissued_hours_rating_modifier)
    # logger.debug(f"after unissued_hours {rate}")

    return max(0, rate)


def get_counts(
    schedule: dict[str, list[db.Pair]], original_data: db.Data, remaining_data: db.Data
) -> dict:
    return {
        "teachers_gaps_count": count_teachers_gaps(original_data, remaining_data),
        "offline_pairs_gaps": count_offline_pairs_gaps(schedule, original_data),
        "overworked_teachers": count_overworked_teachers(schedule),
        "unissued_hours": count_unissued_hours(remaining_data),
    }


# endregion


if __name__ == "__main__":
    logger.info("Запуск оптимизации расписания")
    data = db.ExampleData()
    best_data = None
    best_schedule_obj = None
    best_rating = 0

    count_iterations = int(input("Введите количество итераций: "))
    logger.info(f"Количество итераций: {count_iterations}")
    update_every = 3  # seconds
    progressbar_length = 20
    passed_time = 0
    start_time = time.time()

    for iteration in range(1, count_iterations + 1):
        if (
            time.time() - (passed_time + start_time) > update_every
        ):  # condition: every 1 second
            passed_time = time.time() - start_time
            approx_time = count_iterations * passed_time / iteration
            remaining_time = approx_time - passed_time
            completion_percentage = round((iteration / count_iterations) * 100, 2)
            progressbar = (
                "["
                + (
                    "█" * (int(completion_percentage / 100 * progressbar_length))
                    + "▁"
                    * (
                        progressbar_length
                        - int(completion_percentage / 100 * progressbar_length)
                    )
                )
                + "]"
            )
            best_schedule_counts = get_counts(
                best_schedule_obj.pairs, best_data, best_schedule_obj.remaining_data
            )
            best_schedule_counts_str = (
                f"TG: {best_schedule_counts['teachers_gaps_count']}, "
                f"OPG: {best_schedule_counts['offline_pairs_gaps']}, "
                f"OT: {best_schedule_counts['overworked_teachers']}, "
                f"UH: {best_schedule_counts['unissued_hours']}"
            )
            logger.debug(
                f"Осталось времени: {str(round(remaining_time // 60)).rjust(2, '0') + 'м, ' if remaining_time >= 60 else ''}{str(round(remaining_time % 60)).rjust(2, '0')}с. {progressbar} {str(round(completion_percentage)).rjust(2, '0')}% / ({best_schedule_counts_str})"
            )
        data_copy = shuffle_data(data)
        schedule_obj = schedule_maker.make_full_schedule(data_copy)
        schedule_rating = rate_schedule(
            schedule_obj.pairs, data_copy, schedule_obj.remaining_data
        )
        if schedule_rating > best_rating:
            best_rating = schedule_rating
            del best_schedule_obj
            best_schedule_obj = copy.deepcopy(schedule_obj)
            best_data = copy.deepcopy(data_copy)
        else:
            del schedule_obj

    logger.info(f"Лучшее расписание: {best_rating}")
    schedule_maker.print_schedule(best_schedule_obj.pairs)
    logger.info(f"Teachers gaps: {count_teachers_gaps(best_data, best_schedule_obj.remaining_data)}")
    logger.info(f"Offline pairs gaps: {count_offline_pairs_gaps(best_schedule_obj.pairs, best_data)}")
    logger.info(f"Overworked teachers: {count_overworked_teachers(best_schedule_obj.pairs)}")
    logger.info(f"Unissued hours: {count_unissued_hours(best_schedule_obj.remaining_data)}")
    logger.info("Оптимизация расписания завершена")
