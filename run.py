import sys
from PyQt5.QtWidgets import QApplication
from src import db
from src.window import MainWindow

if __name__ == "__main__":
    if db.check_exists_data():
        data = db.load_data()
        print(f"Запуск программы (№{data.counter})")
    else:
        data = db.ExampleData()
        db.save_data(data)
        print("Запуск программы в первый раз")
    app = QApplication(sys.argv)
    window = MainWindow(data)
    window.show()
    ex_code = app.exec_()
    db.save_data(data)
    sys.exit(ex_code)
