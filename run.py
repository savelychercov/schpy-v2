import sys

from PyQt5.QtWidgets import QApplication

from config.logger import get_logger
from src import db
from src.window import MainWindow

logger = get_logger("main")

if __name__ == "__main__":
    if db.check_exists_data():
        data = db.load_data()
        logger.info(f"Запуск программы (№{data.counter})")
    else:
        data = db.ExampleData()
        db.save_data(data)
        logger.info("Запуск программы в первый раз")
    app = QApplication(sys.argv)
    window = MainWindow(data)
    window.show()
    ex_code = app.exec_()
    db.save_data(data)
    logger.info("Программа завершена")
    sys.exit(ex_code)
