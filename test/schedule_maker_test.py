"""
Набор юнит-тестов для модуля schedule_maker.

Проверяет корректность:
- генерации полного расписания (валидность каждой пары, типы объектов);
- работы с пустыми входными данными;
- распределения аудиторий;
- выборки расписания по преподавателю, группе или дисциплине.

Тесты используют пример данных из db.ExampleData
и гарантируют базовую целостность логики построения расписания.
"""

import unittest

from src import db
from src import schedule_maker as sm


def check_legit_pair(pair: db.Pair, data: db.Data):
    t1 = pair.discipline in data.teachers[pair.teacher].disciplines
    t2 = pair.group in data.teachers[pair.teacher].groups
    t3 = data.teachers_work_hours[pair.teacher].schedule_for_days[pair.day][
        db.TeachersSchedule.get_pair_number(pair.pair_time) - 1
        ]
    t4 = pair.classroom in data.rooms
    t5 = not data.rooms_availability_hours[pair.classroom].schedule_for_days[pair.day][
        db.RoomSchedule.get_pair_number(pair.pair_time) - 1
        ]

    return all([t1, t2, t3, t4, t5])


class ScheduleMakerUnitTest(unittest.TestCase):
    def test_schedule_maker_example(self):
        data: db.Data = db.ExampleData()
        schedule: sm.Schedule = sm.make_full_schedule(data)
        pairs = [pair for group in schedule.pairs.values() for pair in group]

        for pair in pairs:
            self.assertTrue(check_legit_pair(pair, data))
        self.assertIsInstance(schedule, sm.Schedule)
        self.assertGreater(len(schedule.pairs), 0)
        self.assertTrue(all(isinstance(pair, db.Pair) for pair in pairs))

    def test_schedule_maker_empty(self):
        data: db.Data = db.EmptyData()
        schedule: sm.Schedule = sm.make_full_schedule(data)

        self.assertIsInstance(schedule, sm.Schedule)
        self.assertEqual(len(schedule.pairs), 0)

    def test_classroom_distribution(self):
        data: db.Data = db.ExampleData()
        full_schedule, errors = sm.distribute_pairs(data)
        full_schedule = sm.distribute_classrooms(full_schedule, data)
        classrooms = {
            pair.classroom for group in full_schedule.values() for pair in group
        }

        self.assertGreater(len(classrooms), 0)
        self.assertTrue(
            all([classroom in data.rooms.keys() for classroom in classrooms])
        )

    def test_schedule_sampling(self):
        data: db.Data = db.ExampleData()
        schedule: sm.Schedule = sm.make_full_schedule(data)
        sample_value = list(schedule.pairs.values())[0][0].teacher
        sampled_pairs = sm.get_schedule_for("teacher", schedule.pairs, sample_value)

        self.assertTrue(
            all(
                [
                    pair.teacher == sample_value
                    for group in sampled_pairs.values()
                    for pair in group
                ]
            )
        )


if __name__ == "__main__":
    unittest.main()
