"""
GUI-модуль для генерации, редактирования и визуализации учебного расписания.

Модуль содержит следующие основные компоненты:

ScheduleGeneratorWorkerThread
    Фоновый поток, выполняющий многократную генерацию расписаний,
    выбирающий лучшее по рейтингу и передающий результат в основной поток.

ScheduleGeneratorDialog
    Диалоговое окно, позволяющее выбрать количество итераций и следить
    за прогрессом генерации расписания.

InputDataDialog
    Диалог для просмотра и редактирования всех исходных данных:
    групп, дисциплин, преподавателей, аудиторий и их доступности.

ErrorDialog
    Окно отображения ошибок генерации — тех дисциплин и групп,
    для которых не удалось поставить пары, а также оставшихся часов.

MainWindow
    Главное окно приложения. Позволяет запускать генерацию,
    просматривать расписание, выгружать его в Excel, редактировать входные данные
    и просматривать ошибки.

Модуль обеспечивает полный графический интерфейс для работы с расписанием:
от ввода данных и фоновой оптимизационной генерации
до отображения результата и обработки ошибок.
"""

import copy
import datetime
import sys
import time
import traceback
from pprint import pp

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from PyQt5.QtCore import QEvent, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src import best_of
from src import db
from src import schedule_maker


class ScheduleGeneratorWorkerThread(QThread):
    result_ready = pyqtSignal(schedule_maker.Schedule, dict)

    def __init__(self, iterations, data):
        super().__init__()
        self.iterations = iterations
        self.data = data
        self.best_data = None
        self.best_schedule_obj = None
        self.best_rating = 0
        self.best_schedule_counts = None
        self.progress_value = 0
        self.remaining_time = 0
        self.is_running = True

    def run(self):
        start_time = time.time()

        for iteration in range(1, self.iterations + 1):
            if not self.is_running:
                break
            print(f"Итерация {iteration}/{self.iterations}")
            # Обновляем только переменные прогресса
            passed_time = time.time() - start_time
            approx_time = self.iterations * passed_time / iteration
            self.remaining_time = approx_time - passed_time
            self.progress_value = round((iteration / self.iterations) * 100, 2)

            # Основная работа
            data_copy = best_of.shuffle_data(self.data)
            current_schedule_obj = schedule_maker.make_full_schedule(data_copy)
            schedule_rating = best_of.rate_schedule(
                current_schedule_obj.pairs,
                data_copy,
                current_schedule_obj.remaining_data,
            )

            if schedule_rating > self.best_rating:
                self.best_rating = schedule_rating
                del self.best_schedule_obj
                self.best_schedule_obj = copy.deepcopy(current_schedule_obj)
                self.best_data = copy.deepcopy(data_copy)
            else:
                del current_schedule_obj

        if not self.is_running:
            return

        # Завершение работы и отправка результата
        self.best_schedule_counts = best_of.get_counts(
            self.best_schedule_obj.pairs,
            self.best_data,
            self.best_schedule_obj.remaining_data,
        )
        rating = {
            "rate": self.best_rating,
            "teachers_gaps_count": self.best_schedule_counts["teachers_gaps_count"],
            "offline_pairs_gaps": self.best_schedule_counts["offline_pairs_gaps"],
            "overworked_teachers": self.best_schedule_counts["overworked_teachers"],
            "unissued_hours": self.best_schedule_counts["unissued_hours"],
        }
        self.result_ready.emit(self.best_schedule_obj, rating)
        self.stop()

    def stop(self):
        self.is_running = False
        self.quit()


class ScheduleGeneratorDialog(QDialog):
    result_obtained = pyqtSignal(schedule_maker.Schedule, dict)

    def __init__(self, data):
        super().__init__()
        self.data = data
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_progress_bar)
        self.worker_thread = None

        self.result = None
        self.rating = None

        with open(db.resource_path("../css/ScheduleGeneratorDialog.css")) as style_file:
            self.setStyleSheet(style_file.read())
        self.setWindowIcon(QIcon(db.resource_path("../icon.ico")))

        self.setWindowTitle("Генератор лучшего расписания")
        self.setGeometry(100, 100, 400, 300)

        layout = QVBoxLayout()

        self.worker_thread = None
        default_number = 10000
        min_number = 1000
        max_number = 500000

        self.number_label = QLabel(f"Выберите число итераций: {default_number}")
        layout.addWidget(self.number_label)

        self.number_slider = QSlider(Qt.Horizontal)
        self.number_slider.setMinimum(min_number)
        self.number_slider.setMaximum(max_number)
        self.number_slider.setValue(default_number)
        self.number_slider.update()
        self.number_slider.setTickInterval(1000)
        self.number_slider.valueChanged.connect(self.update_number_label)
        layout.addWidget(self.number_slider)

        self.generate_button = QPushButton("Генерация")
        self.generate_button.clicked.connect(self.start_generation)
        layout.addWidget(self.generate_button)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.remaining_time_label = QLabel()
        layout.addWidget(self.remaining_time_label)

        self.setLayout(layout)

    def closeEvent(self, event):
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.stop()
        super().closeEvent(event)

    def start_generation(self):
        self.generate_button.setEnabled(False)
        self.progress_bar.setValue(0)
        selected_number = self.number_slider.value()

        # Запуск рабочего потока и таймера
        self.worker_thread = ScheduleGeneratorWorkerThread(selected_number, self.data)
        self.worker_thread.result_ready.connect(self.handle_result)
        self.worker_thread.finished.connect(self.on_task_finished)
        self.worker_thread.start()

        self.update_timer.start(1000)

    def update_progress_bar(self):
        # Обновление состояния интерфейса на основе данных из потока
        if self.worker_thread:
            self.progress_bar.setValue(int(self.worker_thread.progress_value))
            remaining_time = self.worker_thread.remaining_time
            self.remaining_time_label.setText(

                    f"Осталось времени: {str(round(remaining_time // 59)) + 'м, ' if remaining_time >= 60 else ''}"
                    f"{round(remaining_time % 59)!s}с."

            )

    def update_number_label(self):
        self.number_label.setText(
            f"Выберите число итераций:\n{self.number_slider.value()}"
        )

    def handle_result(self, result, rating):
        self.result = result
        self.rating = rating
        self.result_obtained.emit(result, rating)

    def on_task_finished(self):
        self.generate_button.setEnabled(True)
        self.accept()

    def get_result(self):
        return self.result, self.rating

    def event(self, event):
        if event.type() == QEvent.Type(124):
            self.show_help()
            return True
        return super().event(event)

    def show_help(self):
        # Отображение справки
        help_message = (
            "Справка по использованию программы:\n\n"
            "В этом окне вы можете выбрать количество итераций для генерации лучшего расписания.\n"
            "После выбора количества итераций нажмите кнопку 'Генерация'.\n"
            "Во время генерации расписания будет отображаться прогресс и оставшееся время.\n"
            "После завершения генерации расписания окно будет закрыто.\n"
            "Результат генерации расписания будет доступен таблице.\n\n"
        )
        QMessageBox.information(self, "Справка", help_message)


class InputDataDialog(QDialog):
    def __init__(self):
        super().__init__(parent=None)

        with open(db.resource_path("../css/InputDataDialog.css")) as f:
            self.setStyleSheet(f.read())
        self.setWindowIcon(QIcon(db.resource_path("../icon.ico")))

        self.vars_to_redact = {
            "Смены групп": "groups_shift",
            "КУГ": "discipline_hours",
            "Преподаватели": "teachers",
            "Аудитории": "rooms",
            "Расписание\nпреподавателей": "teachers_work_hours",
            "Расписание\nаудиторий": "rooms_availability_hours",
        }

        self.setWindowTitle("Ввод данных")
        self.setGeometry(100, 100, 1200, 600)
        self.setWindowFlags(Qt.Window)

        self.layout = QHBoxLayout(self)

        self.variable_list = QListWidget()
        self.variable_list.setFixedWidth(250)
        self.variable_list.addItems(list(self.vars_to_redact.keys()))
        self.variable_list.currentItemChanged.connect(self.display_variable_data)
        self.layout.addWidget(self.variable_list)

        self.data_table = QTableWidget()
        self.layout.addWidget(self.data_table)

        self.button_layout = QVBoxLayout()

        self.add_row_button = QPushButton("Добавить строку")
        self.add_row_button.clicked.connect(self.add_row)
        self.button_layout.addWidget(self.add_row_button)

        self.delete_selected_rows_button = QPushButton("Удалить выделенные строки")
        self.delete_selected_rows_button.clicked.connect(self.delete_selected_rows)
        self.button_layout.addWidget(self.delete_selected_rows_button)

        self.save_button = QPushButton("Сохранить изменения")
        self.save_button.clicked.connect(self.save_changes)
        self.button_layout.addWidget(self.save_button)

        self.clear_data_button = QPushButton("Очистить все данные")
        self.clear_data_button.clicked.connect(self.clear_data)
        self.button_layout.addWidget(self.clear_data_button)

        self.load_test_data_button = QPushButton("Загрузить тестовые данные")
        self.load_test_data_button.clicked.connect(self.load_test_data)
        self.button_layout.addWidget(self.load_test_data_button)

        self.back_button = QPushButton("Назад")
        self.back_button.clicked.connect(self.close)
        self.button_layout.addWidget(self.back_button)

        self.var_help_label = QLabel()
        self.var_help_label.setFixedWidth(265)
        self.var_help_label.setWordWrap(True)
        self.button_layout.addWidget(self.var_help_label)

        self.layout.addLayout(self.button_layout)

        self.current_variable = None

    def load_test_data(self):
        resp = QMessageBox.question(
            self,
            "Подтверждение",
            "Вы уверены, что хотите загрузить тестовые данные? Это действие нельзя отменить",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp == QMessageBox.Yes:
            self.data = db.ExampleData()
            self.display_variable_data(self.data_table.currentItem())

    def clear_data(self):
        resp = QMessageBox.question(
            self,
            "Подтверждение",
            "Вы уверены, что хотите очистить все данные?\nЭто действие нельзя отменить",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp == QMessageBox.Yes:
            self.data = db.EmptyData()
            self.display_variable_data(self.data_table.currentItem())

    def delete_selected_rows(self):
        resp = QMessageBox.question(
            self,
            "Подтверждение",
            "Удалить выделенные строки?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        selected_indexes = self.data_table.selectionModel().selectedRows()
        selected_rows = sorted(
            [index.row() for index in selected_indexes], reverse=True
        )
        for row in selected_rows:
            self.data_table.model().removeRow(row)

    def add_row(self):
        row = self.data_table.rowCount()
        self.data_table.insertRow(row)

        if self.current_variable == "discipline_hours":
            dropdown = QComboBox()
            dropdown.addItems(self.data.groups_shift.keys())
            self.data_table.setCellWidget(row, 0, dropdown)
        elif self.current_variable == "groups_shift":
            self.data_table.setItem(row, 0, QTableWidgetItem("Группа"))
            self.data_table.setItem(row, 1, QTableWidgetItem("Номер смены"))
        elif self.current_variable == "teachers":
            self.data_table.setItem(row, 0, QTableWidgetItem("ФИО"))
            self.data_table.setItem(
                row, 1, QTableWidgetItem("Дисциплины через запятую")
            )
            self.data_table.setItem(row, 2, QTableWidgetItem("Группы через запятую"))
        elif self.current_variable == "rooms":
            self.data_table.setItem(row, 0, QTableWidgetItem("Аудитория"))
            self.data_table.setItem(row, 1, QTableWidgetItem("Да / Нет"))
        elif self.current_variable == "teachers_work_hours":
            self.data_table.setItem(row, 0, QTableWidgetItem("ФИО"))
        elif self.current_variable == "rooms_availability_hours":
            self.data_table.setItem(row, 0, QTableWidgetItem("Аудитория"))

        if self.current_variable not in [
            "teachers_work_hours",
            "rooms_availability_hours",
        ]:
            self.data_table.resizeColumnsToContents()
            return
        num_pairs = len(self.data.teachers_schedule_time)
        days_of_week = list(self.data.days)

        for col, day in enumerate(days_of_week, start=1):
            day_schedule = [False] * num_pairs

            cell_widget = QWidget()
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.setContentsMargins(0, 0, 0, 0)

            for slot in day_schedule:
                check_box = QCheckBox()
                check_box.setChecked(slot)
                cell_layout.addWidget(check_box)

            cell_widget.setLayout(cell_layout)
            self.data_table.setCellWidget(row, col, cell_widget)

        self.data_table.resizeColumnsToContents()

    def display_variable_data(self, current):
        if not current:
            return

        variable_name = self.vars_to_redact[current.text()]
        self.current_variable = variable_name
        variable_data = getattr(self.data, variable_name)

        self.data_table.setRowCount(0)

        if variable_name == "groups_shift":
            self.var_help_label.setText(
                "Здесь можно добавить группы для которых будет создаваться расписание"
            )
            headers = ["Группа", "Смена"]
            self.data_table.setColumnCount(len(headers))
            self.data_table.setHorizontalHeaderLabels(headers)
            row = 0
            for group, schedule in variable_data.items():
                shift = None
                # Определяем смену, исходя из расписания
                if schedule == self.data.schedule_time_shift_1:
                    shift = "1"
                elif schedule == self.data.schedule_time_shift_2:
                    shift = "2"
                elif schedule == self.data.schedule_time_shift_3:
                    shift = "3"

                self.data_table.insertRow(row)
                self.data_table.setItem(row, 0, QTableWidgetItem(group))
                self.data_table.setItem(row, 1, QTableWidgetItem(shift))
                row += 1

        elif variable_name == "discipline_hours":
            self.var_help_label.setText(
                "Здесь можно добавить дисциплины и количество часов которые "
                "нужно выставить на неделю, если дисциплина не нужна на неделе, "
                "можно поставить ей 0 часов."
            )
            self.data_table.setColumnCount(3)
            self.data_table.setHorizontalHeaderLabels(["Группа", "Дисциплина", "Часы"])
            row = 0
            for group, disciplines in variable_data.items():
                for discipline, hours in disciplines.items():
                    self.data_table.insertRow(row)
                    self.data_table.setItem(row, 0, QTableWidgetItem(group))
                    self.data_table.setItem(row, 1, QTableWidgetItem(discipline))
                    self.data_table.setItem(row, 2, QTableWidgetItem(str(hours)))
                    row += 1

        elif variable_name == "teachers":
            self.var_help_label.setText(
                "Здесь можно добавить преподавателей, дисциплины которые они ведут "
                "и группы у которых они ведут.\nЕсли преподаватель "
                "ведет разные дисциплины у разных групп, создайте преподавателей с "
                'одинаковыми значениями "Имени" и задайте разные дисциплины и группы.'
            )
            self.data_table.setColumnCount(3)
            self.data_table.setHorizontalHeaderLabels(["Имя", "Дисциплины", "Группы"])
            row = 0
            for name, presets in variable_data.items():
                for teacher in presets:
                    self.data_table.insertRow(row)
                    self.data_table.setItem(row, 0, QTableWidgetItem(name))
                    self.data_table.setItem(
                        row, 1, QTableWidgetItem(", ".join(teacher.disciplines))
                    )
                    self.data_table.setItem(
                        row, 2, QTableWidgetItem(", ".join(teacher.groups))
                    )
                    row += 1

        elif variable_name == "rooms":
            self.var_help_label.setText(
                "Здесь можно добавить аудитории в которых будут проводиться занятия"
            )
            self.data_table.setColumnCount(2)
            self.data_table.setHorizontalHeaderLabels(["Аудитория", "Онлайн"])
            row = 0
            for room, room_obj in variable_data.items():
                self.data_table.insertRow(row)
                self.data_table.setItem(row, 0, QTableWidgetItem(room))
                self.data_table.setItem(
                    row, 1, QTableWidgetItem("Да" if room_obj.is_online else "Нет")
                )
                row += 1

        elif variable_name in ["teachers_work_hours", "rooms_availability_hours"]:
            if variable_name == "teachers_work_hours":
                self.var_help_label.setText(
                    "Здесь можно отметить часы работы преподавателей, "
                    "они идут по порядку слева направо"
                )
            else:
                self.var_help_label.setText(
                    "Здесь можно отметить доступность аудиторий, "
                    "галочки обозначают что аудитория занята!"
                )
            self._setup_schedule_table(variable_data)

        self.data_table.setEditTriggers(QTableWidget.DoubleClicked)
        self.data_table.resizeColumnsToContents()

    def _setup_schedule_table(self, schedule_data):
        days_of_week = list(self.data.days)
        num_pairs = len(self.data.teachers_schedule_time)

        # Устанавливаем столбцы: один для имени, остальные для расписания по дням
        self.data_table.setColumnCount(1 + len(days_of_week))
        headers = ["Имя"] + days_of_week
        self.data_table.setHorizontalHeaderLabels(headers)

        for row, (name, schedule) in enumerate(schedule_data.items()):
            self.data_table.insertRow(row)
            self.data_table.setItem(row, 0, QTableWidgetItem(name))

            for col, day in enumerate(days_of_week, start=1):
                day_schedule = schedule.schedule_for_days.get(day, [False] * num_pairs)

                cell_widget = QWidget()
                cell_layout = QHBoxLayout(cell_widget)
                cell_layout.setContentsMargins(0, 0, 0, 0)

                # Создаем по одному QCheckBox для каждой пары в день
                for slot in day_schedule:
                    check_box = QCheckBox()
                    check_box.setChecked(slot)
                    cell_layout.addWidget(check_box)

                cell_widget.setLayout(cell_layout)
                self.data_table.setCellWidget(row, col, cell_widget)

    def _save_schedule_changes(self, schedule_data):
        for row in range(self.data_table.rowCount()):
            name = self.data_table.item(row, 0).text()

            updated_schedule = {}
            for col in range(1, self.data_table.columnCount()):
                day = self.data_table.horizontalHeaderItem(col).text()

                cell_widget = self.data_table.cellWidget(row, col)
                day_schedule = [
                    check_box.isChecked()
                    for check_box in cell_widget.findChildren(QCheckBox)
                ]

                updated_schedule[day] = day_schedule

            if name in schedule_data:
                schedule_data[name].schedule_for_days = updated_schedule
            elif self.current_variable == "teachers_work_hours":
                schedule_data[name] = db.TeachersSchedule(
                    *list(updated_schedule.values())
                )
            elif self.current_variable == "rooms_availability_hours":
                schedule_data[name] = db.RoomSchedule(
                    *list(updated_schedule.values())
                )

    def save_changes(self):
        if self.current_variable is None:
            return

        invalid_data = []
        table_name = self.current_variable
        ru_table_name = next(
            (key for key, value in self.vars_to_redact.items() if value == table_name),
            None,
        )

        try:
            variable_data = getattr(self.data, table_name)

            if table_name == "groups_shift":
                variable_data = {}  # Перезаписываем переменную

                for row in range(self.data_table.rowCount()):
                    try:
                        group = self.data_table.item(row, 0).text()
                        shift = int(self.data_table.item(row, 1).text())

                        # Определяем расписание по номеру смены
                        if shift == 1:
                            schedule = self.data.schedule_time_shift_1
                        elif shift == 2:
                            schedule = self.data.schedule_time_shift_2
                        elif shift == 3:
                            schedule = self.data.schedule_time_shift_3
                        else:
                            raise ValueError("Неверный номер смены")

                        # Сохраняем расписание для группы
                        variable_data[group] = schedule
                    except (ValueError, AttributeError, IndexError):
                        # Собираем данные некорректной строки
                        row_data = [
                            self.data_table.item(row, col).text()
                            if self.data_table.item(row, col)
                            else ""
                            for col in range(self.data_table.columnCount())
                        ]
                        invalid_data.append(row_data)

            elif table_name == "discipline_hours":
                variable_data = {}
                for row in range(self.data_table.rowCount()):
                    try:
                        if self.data_table.item(row, 0) is None:
                            group = self.data_table.cellWidget(row, 0).currentText()
                        else:
                            group = self.data_table.item(row, 0).text()
                        discipline = self.data_table.item(row, 1).text()
                        hours = int(self.data_table.item(row, 2).text())
                        if group not in variable_data:
                            variable_data[group] = {}
                        variable_data[group][discipline] = hours
                    except (ValueError, AttributeError):
                        row_data = [
                            self.data_table.item(row, col).text()
                            for col in range(self.data_table.columnCount())
                        ]
                        invalid_data.append(row_data)

            elif table_name == "teachers":
                variable_data = {}
                for row in range(self.data_table.rowCount()):
                    try:
                        name = self.data_table.item(row, 0).text()
                        disciplines = set(
                            self.data_table.item(row, 1).text().split(", ")
                        )
                        groups = set(self.data_table.item(row, 2).text().split(", "))
                        if name not in variable_data:
                            variable_data[name] = [
                                db.Teacher(name, disciplines, groups)
                            ]
                        else:
                            variable_data[name].append(
                                db.Teacher(name, disciplines, groups)
                            )

                        if name not in self.data.teachers_work_hours.keys():
                            self.data.teachers_work_hours[name] = db.TeachersSchedule()
                    except AttributeError:
                        row_data = [
                            self.data_table.item(row, col).text()
                            for col in range(self.data_table.columnCount())
                        ]
                        invalid_data.append(row_data)

                data_copy = copy.deepcopy(self.data.teachers_work_hours)
                for teacher in self.data.teachers_work_hours.keys():
                    if teacher not in variable_data.keys():
                        data_copy.pop(teacher)
                self.data.teachers_work_hours = data_copy
                pp(variable_data)

            elif table_name == "rooms":
                variable_data = {}
                for row in range(self.data_table.rowCount()):
                    try:
                        room = self.data_table.item(row, 0).text()
                        is_online = self.data_table.item(row, 1).text() == "Да"
                        variable_data[room] = db.Room(is_online)
                        if room not in self.data.rooms_availability_hours.keys():
                            self.data.rooms_availability_hours[room] = db.RoomSchedule()
                    except AttributeError:
                        row_data = [
                            self.data_table.item(row, col).text()
                            for col in range(self.data_table.columnCount())
                        ]
                        invalid_data.append(row_data)

                data_copy = copy.deepcopy(self.data.rooms_availability_hours)
                for room in self.data.rooms_availability_hours.keys():
                    if room not in variable_data.keys():
                        data_copy.pop(room)
                self.data.rooms_availability_hours = data_copy

            elif table_name in ["teachers_work_hours", "rooms_availability_hours"]:
                try:
                    self._save_schedule_changes(variable_data)
                except Exception as e:
                    QMessageBox.warning(
                        self, "Ошибка", f"Ошибка при сохранении расписания: {e!s}"
                    )

            setattr(self.data, table_name, variable_data)

        except AttributeError:
            QMessageBox.critical(
                self,
                "Ошибка",
                "Не удалось сохранить изменения (В таблице есть пустые поля)",
            )
            return

        except Exception as e:
            QMessageBox.critical(
                self,
                "Критическая ошибка",
                f"Не удалось сохранить изменения ({type(e).__name__}): {e!s}\n\n{traceback.format_exc()}",
            )
            return

        if invalid_data:
            # Подготовка информации о первых трех ошибках
            error_message = f"Обнаружены ошибки в таблице '{ru_table_name}'. Проверьте следующие строки:\n"
            for i, row_data in enumerate(invalid_data[:3]):
                error_message += f"\nСтрока {i + 1}: " + ", ".join(row_data)

            QMessageBox.warning(self, "Ошибка данных", error_message)
        else:
            db.save_data(self.data)
            QMessageBox.information(
                self,
                "Сохранение",
                f"Данные в таблице '{ru_table_name}' успешно сохранены.",
            )

    def event(self, event):
        if event.type() == QEvent.Type(124):
            self.show_help()
            return True
        return super().event(event)

    def show_help(self):
        # Отображение справки
        help_message = (
            "Справка по использованию программы:\n\n"
            "В этом окне можно ввести данные для расписания,\nкоторые будут использоваться при его генерации."
            "\n\n"
            "В левой части окна отображается список таблиц, в которых можно ввести данные.\n"
            "Выберите таблицу, в которую хотите ввести данные и заполните ее.\n\n"
            "В середине окна отображается таблица с данными.\n"
            "Для сохранения изменений в текущей таблице нажмите кнопку 'Сохранить'.\n\n"
            "Для выхода нажмите кнопку 'Назад' (данные не сохранятся если не была нажата кнопка 'Сохранить')."
        )
        QMessageBox.information(self, "Справка", help_message)


class ErrorDialog(QDialog):
    def __init__(self, errors: list, remaining_data: db.Data):
        super().__init__()
        self.setWindowTitle("Ошибки при генерации расписания")
        self.setGeometry(
            100, 100, 800, 500
        )  # Увеличиваем ширину окна для списка оставшихся часов
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowContextHelpButtonHint
        )  # Добавляем кнопку справки

        # Загрузка стиля
        with open(db.resource_path("../css/ErrorDialog.css")) as f:
            self.setStyleSheet(f.read())
        self.setWindowIcon(QIcon(db.resource_path("../icon.ico")))

        # Основной макет с горизонтальным расположением для левой и правой частей
        main_layout = QHBoxLayout(self)

        # Левая часть (список ошибок и информация о текущей ошибке)
        left_layout = QVBoxLayout()
        self.errors = errors

        # Список ошибок
        self.error_list_widget = QListWidget()
        self.error_list_widget.addItems(
            [
                f"{i + 1} / Группа: {error.group}, Дисциплина: {error.discipline}"
                for i, error in enumerate(errors)
            ]
        )
        self.error_list_widget.currentItemChanged.connect(self.display_error_info)

        # Заголовок и описание ошибок
        self.help_text = QLabel(
            "Невозможно поставить пары для данных дисциплин и групп:"
        )
        left_layout.addWidget(self.help_text)
        left_layout.addWidget(self.error_list_widget)

        self.group_label = QLabel("| Группа: ")
        self.discipline_label = QLabel("| Дисциплина: ")
        self.hours_label = QLabel("| Оставшиеся часы: ")
        left_layout.addWidget(self.group_label)
        left_layout.addWidget(self.discipline_label)
        left_layout.addWidget(self.hours_label)

        main_layout.addLayout(left_layout)

        # Правая часть (список дисциплин с оставшимися часами)
        right_layout = QVBoxLayout()
        self.remaining_hours_list_widget = QListWidget()

        # Заголовок для оставшихся часов
        remaining_hours_label = QLabel("Дисциплины с оставшимися часами:")
        right_layout.addWidget(remaining_hours_label)
        right_layout.addWidget(self.remaining_hours_list_widget)

        # Добавление данных об оставшихся часах в виджет
        for group, disciplines in remaining_data.discipline_hours.items():
            for discipline, hours in disciplines.items():
                if hours > 0:
                    self.remaining_hours_list_widget.addItem(
                        f"Группа: {group},\nДисциплина: {discipline},\nОсталось часов: {hours}"
                    )

        self.back_button = QPushButton("Назад")
        self.back_button.clicked.connect(self.close)
        right_layout.addWidget(self.back_button)

        main_layout.addLayout(right_layout)

    def display_error_info(self, current):
        def pair_text(count):
            if count % 10 == 1:
                return "пара"
            if count % 10 in [2, 3, 4]:
                return "пары"
            return "пар"

        if current:
            current_error = self.errors[int(current.text().split("/")[0].strip()) - 1]
            self.group_label.setText(f"| Группа: {current_error.group}")
            self.discipline_label.setText(f"| Дисциплина: {current_error.discipline}")
            self.hours_label.setText(
                f"| Оставшиеся часы: {current_error.hours} (= {current_error.hours // 2} {pair_text(current_error.hours // 2)})"
            )

    def event(self, event):
        if event.type() == QEvent.Type(124):
            self.show_help()
            return True
        return super().event(event)

    def show_help(self):
        # Отображение справки
        help_message = (
            "В этом окне отображаются ошибки, возникшие при генерации расписания.\n\n"
            "Список вверху содержит информацию о группе и дисциплине, для которой не удалось "
            "поставить пары. Выберите элемент из списка, чтобы увидеть подробные данные "
            "о выбранной ошибке ниже.\n\n"
            "С правой стороны отображается список дисциплин с оставшимися часами, "
            "которые ещё не были распределены в расписании."
        )
        QMessageBox.information(self, "Справка", help_message)


class MainWindow(QMainWindow):
    _instance = None

    def __init__(self, data=None):
        MainWindow._instance = self
        self.data = data
        self.current_schedule: schedule_maker.Schedule = None
        self.remaining_data = None
        self.rating = None
        self.errors = []
        self.empty_table_message = "Здесь отобразится сгенерированное расписание"
        self.table_headers = [
            "Группа",
            "День",
            "Время",
            "Форма",
            "Предмет",
            "Педагог",
            "Каб.",
        ]
        self.current_cell = None
        self.input_dialog = None

        super().__init__()

        self.setWindowTitle("Составление расписания")
        self.setWindowIcon(QIcon(db.resource_path("../icon.ico")))
        self.setGeometry(100, 100, 1400, 800)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.layout = QHBoxLayout(self.central_widget)

        self.table_widget = QTableWidget(1, 1)
        self.table_widget.setHorizontalHeaderLabels(["Расписание"])
        self.table_widget.setItem(0, 0, QTableWidgetItem(self.empty_table_message))
        self.table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_widget.cellClicked.connect(self.on_cell_click)

        self.button_layout = QVBoxLayout()

        self.generate_schedule_button = QPushButton("Сгенерировать расписание")
        self.generate_schedule_button.clicked.connect(self.generate_schedule)
        self.button_layout.addWidget(self.generate_schedule_button)

        self.error_button = QPushButton(f"Ошибки: {len(self.errors)}")
        self.error_button.setEnabled(False)
        self.error_button.clicked.connect(self.show_errors)
        self.button_layout.addWidget(self.error_button)

        self.export_schedule_button = QPushButton("Выгрузить расписание")
        self.export_schedule_button.clicked.connect(self.export_schedule)
        self.button_layout.addWidget(self.export_schedule_button)

        self.input_data_button = QPushButton("Ввод данных")
        self.input_data_button.clicked.connect(self.input_data)
        self.button_layout.addWidget(self.input_data_button)

        self.sort_by_button = QPushButton("Сформировать по...")
        self.sort_by_button.clicked.connect(self.sort_by)
        self.sort_by_button.setEnabled(False)
        self.button_layout.addWidget(self.sort_by_button)

        self.generate_best_schedule_button = QPushButton(
            "Сгенерировать лучшее расписание"
        )
        self.generate_best_schedule_button.clicked.connect(self.generate_best_schedule)
        self.button_layout.addWidget(self.generate_best_schedule_button)

        self.schedule_rating_label = QLabel()
        self.button_layout.addWidget(self.schedule_rating_label)

        self.layout.addWidget(self.table_widget)
        self.layout.addLayout(self.button_layout)

        self.button_layout.addStretch()

        with open(db.resource_path("../css/MainWindow.css")) as f:
            self.setStyleSheet(f.read())
        self.resize_columns()

        if self.data is None:
            resp = QMessageBox.warning(
                self,
                "Информация",
                "Данные не найдены. Загрузите тестовые или заполните их в окне 'Ввод данных'\nЗагрузить тестовый набор?",
                QMessageBox.Ok | QMessageBox.Cancel,
            )

            if resp == QMessageBox.Ok:
                self.data = db.ExampleData()
            else:
                self.data = db.EmptyData()

    def schedule_rating_label_update(self, rating: dict[str, int]):
        names = {
            "rate": "Рейтинг",
            "teachers_gaps_count": "Окна у преподавателей",
            "offline_pairs_gaps": "Пропущенные пары",
            "overworked_teachers": "Перегруженные преподаватели",
            "unissued_hours": "Неиспользованные часы",
        }
        rating = {names[k]: v for k, v in rating.items()}
        self.schedule_rating_label.setText(
            f"Результат:\n - {'\n - '.join([f'{k}: {v}' for k, v in rating.items()])}"
        )

    def on_cell_click(self, row, column):
        sort_by = {
            "Группа": "group",
            "День": "day",
            "Форма": "pair_type",
            "Предмет": "discipline",
            "Педагог": "teacher",
            "Каб.": "classroom",
        }
        if self.current_cell == "all":
            return
        self.current_cell = {
            "row": row,
            "column": column,
            "value": self.table_widget.item(row, column).text(),
            "header": self.table_widget.horizontalHeaderItem(column).text(),
        }
        if self.current_cell["header"] in sort_by:
            self.sort_by_button.setText(
                f"Сформировать по\n{self.current_cell['value']}"
            )
            self.sort_by_button.setEnabled(True)
        else:
            self.sort_by_button.setText("Сформировать по...")
            self.sort_by_button.setEnabled(False)

    def resize_columns(self):
        self.table_widget.resizeColumnsToContents()

    def set_pairs_to_table(self, pairs: dict[str, list[db.Pair]]):
        self.table_widget.setRowCount(0)
        self.table_widget.setColumnCount(len(self.table_headers))
        self.table_widget.setHorizontalHeaderLabels(self.table_headers)

        rows: list[str] = []
        for group, pairs_list in pairs.items():
            for pair in pairs_list:
                rows.append(
                    [
                        group,
                        pair.day,
                        pair.pair_time.get_str(),
                        pair.pair_type,
                        pair.discipline,
                        pair.teacher,
                        pair.classroom,
                    ]
                )

        for row in rows:
            current_row = self.table_widget.rowCount()
            self.table_widget.insertRow(current_row)
            for column in range(len(row)):
                self.table_widget.setItem(
                    current_row, column, QTableWidgetItem(row[column])
                )

        self.resize_columns()

    def generate_schedule(self):
        sch = schedule_maker.make_full_schedule(self.data)
        self.current_schedule = sch
        self.errors = sch.errors
        self.remaining_data = sch.remaining_data
        rating = {
            "rate": best_of.rate_schedule(sch.pairs, self.data, sch.remaining_data)
        } | best_of.get_counts(sch.pairs, self.data, sch.remaining_data)
        if self.rating is not None and self.rating["rate"] > rating["rate"]:
            resp = QMessageBox.question(
                self,
                "Внимание",
                f"Новое расписание получилось хуже предыдущего (Рейтинг {rating['rate']})\nПрименить новое расписание?",
                buttons=QMessageBox.Ok | QMessageBox.Cancel,
            )
            if resp == QMessageBox.Cancel:
                return
        self.rating = rating
        self.schedule_rating_label_update(self.rating)
        self.set_pairs_to_table(sch.pairs)
        self.resize_columns()
        self.error_button.setText(f"Ошибки: {len(self.errors)}")
        self.error_button.setEnabled(len(self.errors) > 0)

    def show_errors(self):
        if self.errors:
            error_dialog = ErrorDialog(self.errors, self.remaining_data)
            error_dialog.exec_()

    def export_schedule(self):
        class ExportException(Exception):
            pass

        try:
            row_count = self.table_widget.rowCount()
            column_count = self.table_widget.columnCount()

            if self.current_schedule is None:
                raise ExportException("Расписание не сформировано")

            file_name = f"ExportSchedule{int(self.rating['rate'])}{datetime.datetime.now().strftime('%H%M%S')}.xlsx"

            exp_data = []
            for row in range(row_count):
                row_data = []
                for column in range(column_count):
                    item = self.table_widget.item(row, column)
                    row_data.append(item.text() if item else "")
                exp_data.append(row_data)

            headers = [
                self.table_widget.horizontalHeaderItem(i).text()
                for i in range(column_count)
            ]

            workbook = Workbook()
            sheet = workbook.active

            for col_num, header in enumerate(headers, 1):  # fill headers
                sheet.cell(row=1, column=col_num, value=header)

            for row_num, row_data in enumerate(exp_data, 2):  # fill data
                for col_num, value in enumerate(row_data, 1):
                    sheet.cell(row=row_num, column=col_num, value=value)

            sheet.cell(
                row=1,
                column=column_count + 2,
                value=f"Невозможно поставить пары: {len(self.errors)}",
            )
            err_headers = ["Группа", "Предмет", "Остаток часов"]
            for col_num, header in enumerate(
                err_headers, column_count + 2
            ):  # fill error headers
                sheet.cell(row=2, column=col_num, value=header)

            for err_num, err in enumerate(self.errors):  # fill error data
                sheet.cell(row=3 + err_num, column=column_count + 2, value=err.group)
                sheet.cell(
                    row=3 + err_num, column=column_count + 3, value=err.discipline
                )
                sheet.cell(row=3 + err_num, column=column_count + 4, value=err.hours)

            sheet.cell(
                row=len(self.errors) + 4,
                column=column_count + 2,
                value=f"Рейтинг: {self.rating['rate']}",
            )
            sheet.cell(
                row=len(self.errors) + 5,
                column=column_count + 2,
                value=f"Окна у преподавателей: {self.rating['teachers_gaps_count']}",
            )
            sheet.cell(
                row=len(self.errors) + 6,
                column=column_count + 2,
                value=f"Пропущенные пары: {self.rating['offline_pairs_gaps']}",
            )
            sheet.cell(
                row=len(self.errors) + 7,
                column=column_count + 2,
                value=f"Перегруженные преподаватели: {self.rating['overworked_teachers']}",
            )
            sheet.cell(
                row=len(self.errors) + 8,
                column=column_count + 2,
                value=f"Неиспользованные часы: {self.rating['unissued_hours']}",
            )

            for col in range(
                1, column_count + len(err_headers) + 4
            ):  # adjust column width
                max_length = 0
                column_letter = get_column_letter(col)
                for row in range(1, row_count + 2):
                    cell_value = sheet[f"{column_letter}{row}"].value
                    if cell_value:
                        max_length = max(max_length, len(str(cell_value)))
                adjusted_width = max_length + 2
                sheet.column_dimensions[column_letter].width = adjusted_width

            workbook.save(file_name)
            resp = QMessageBox.information(
                self,
                "Успех",
                "Расписание успешно выгружено\nОткрыть xlsx файл?",
                buttons=QMessageBox.Ok | QMessageBox.Cancel,
            )

            if resp == QMessageBox.Ok:
                import os

                os.startfile(file_name)
        except ExportException:
            QMessageBox.warning(
                self, "Ошибка", "Сгенерируйте расписание перед выгрузкой"
            )
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", str(e))
            raise e

    def sort_by(self):
        if self.current_cell == "all":
            self.set_pairs_to_table(self.current_schedule.pairs)
            self.current_cell = None
            self.sort_by_button.setText("Сформировать по...")
            self.sort_by_button.setEnabled(False)
            return
        if self.current_schedule is None:
            QMessageBox.warning(
                self, "Ошибка", "Сгенерируйте расписание перед сортировкой"
            )
            return
        sort_by = {
            "Группа": "group",
            "День": "day",
            "Форма": "pair_type",
            "Предмет": "discipline",
            "Педагог": "teacher",
            "Каб.": "classroom",
        }
        sorted_pairs = schedule_maker.get_schedule_for(
            sort_by[self.current_cell["header"]],
            self.current_schedule.pairs,
            self.current_cell["value"],
        )
        sorted_pairs = schedule_maker.sorted_pairs(sorted_pairs)
        self.set_pairs_to_table(sorted_pairs)
        self.current_cell = "all"
        self.sort_by_button.setText("Полное расписание")
        self.sort_by_button.setEnabled(True)

    def generate_best_schedule(self):
        dialog = ScheduleGeneratorDialog(self.data)
        dialog.result_obtained.connect(self.handle_generator_result)
        if dialog.exec_() == QDialog.Accepted:
            result, rating = dialog.get_result()
            self.handle_generator_result(result, rating)

    def input_data(self):
        if not self.input_dialog:  # Создаем окно только если оно еще не создано
            self.input_dialog = InputDataDialog()
        self.input_dialog.show()

    def handle_generator_result(
        self, result: schedule_maker.Schedule, rating: dict[str, int]
    ):
        if self.rating is not None and self.rating["rate"] > rating["rate"]:
            resp = QMessageBox.question(
                self,
                "Внимание",
                f"Новое расписание получилось хуже предыдущего (Рейтинг {rating['rate']})\nПрименить новое расписание?",
                buttons=QMessageBox.Ok | QMessageBox.Cancel,
            )
            if resp == QMessageBox.Cancel:
                return

        self.current_schedule = result
        self.errors = result.errors
        self.remaining_data = result.remaining_data
        self.rating = rating
        self.set_pairs_to_table(result.pairs)
        self.resize_columns()
        self.error_button.setText(f"Ошибки: {len(self.errors)}")
        self.error_button.setEnabled(len(self.errors) > 0)
        self.schedule_rating_label_update(self.rating)


def global_exception_handler(exctype, value, tb: traceback):  # noqa
    print("Произошла необработанная ошибка:", value)
    with open("../error_log.txt", "a", encoding="utf-8") as f:
        f.write(
            f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Произошла не обработанная ошибка: {value}\n\n"
        )
    if hasattr(MainWindow, '_instance') and MainWindow._instance.data:
        db.save_data(MainWindow._instance.data)
    sys.__excepthook__(exctype, value, traceback)
    sys.exit(1)


sys.excepthook = global_exception_handler

if __name__ == "__main__":
    if db.check_exists_data():
        data = db.load_data()
        print(f"Запуск программы (№{data.counter})")
    else:
        data = db.ExampleData()
        print("Запуск программы в первый раз")
    app = QApplication(sys.argv)
    window = MainWindow(data)
    window.show()
    ex_code = app.exec_()
    db.save_data(data)
    sys.exit(ex_code)
