"""
Создает .exe файл в папке build
"""

import datetime
import os
import shutil
import sys
import tempfile
import glob

import PyInstaller.__main__

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from src import db

# ОЧИСТКА ВРЕМЕННЫХ ПАПОК PYINSTALLER
temp_dir = tempfile.gettempdir()
mei_folders = glob.glob(os.path.join(temp_dir, "_MEI*"))
for folder in mei_folders:
    try:
        shutil.rmtree(folder, ignore_errors=True)
        print(f"Cleaned up: {folder}")
    except:
        pass

dist_path = os.path.abspath("dist")
title = "SchPy"
start_file = os.path.abspath("../src/window.py")
icon_name = os.path.abspath("../icon.ico")
no_console = True
run_exe = True
current_directory = os.path.dirname(os.path.abspath(__file__))

major_version = "1"
minor_version = "3"
patch_version = "0"
build_number = db.load_data().counter
debug = False
company_name = "savelychercov"
product_name = "ScheduleMaker"
description = "App for creating schedule for college"

version_info_path = os.path.join(dist_path, "version_info.txt")

version_template = f"""
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major_version}, {minor_version}, {patch_version}, {build_number}),
    prodvers=({major_version}, {minor_version}, {patch_version}, {build_number}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'{company_name}'),
        StringStruct(u'FileDescription', u'{description}'),
        StringStruct(u'FileVersion', u'{major_version}.{minor_version}.{patch_version}.{build_number}'),
        StringStruct(u'InternalName', u'{title}'),
        StringStruct(u'LegalCopyright', u'© {datetime.datetime.now().year} {company_name}'),
        StringStruct(u'OriginalFilename', u'{title}.exe'),
        StringStruct(u'ProductName', u'{product_name}'),
        StringStruct(u'ProductVersion', u'{major_version}.{minor_version}.{patch_version}.{build_number}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""

files = [
    "../icon.ico",
    "../src/schedule_maker.py",
    "../src/best_of.py",
    "../src/db.py",
    "../src/schemas.py",
    "../css/MainWindow.css",
    "../css/InputDataDialog.css",
    "../css/ScheduleGeneratorDialog.css",
    "../css/ErrorDialog.css",
]

command = [
    start_file,
    "--noconfirm",
    "--onefile",
    f"--icon={icon_name}",
    f"--name={title}",
    "--clean",
    f"--distpath={dist_path}",
    f"--workpath={os.path.join(dist_path, 'build_temp')}",
    f"--specpath={dist_path}",
    f"--version-file={version_info_path}",
]

if no_console:
    command.append("--noconsole")

# Добавляем все файлы
for filename in files:
    full_path = os.path.join(current_directory, filename)
    full_path = os.path.abspath(full_path)
    if not os.path.exists(full_path):
        print(f"Warning: File not found: {full_path}")
        continue
    print("Adding file:", full_path)

    # Определяем место назначения
    if filename.endswith('.css'):
        dest = "css"
    elif filename.endswith('.py'):
        dest = "."
    else:
        dest = "."

    command.append(f"--add-data={full_path}{os.pathsep}{dest}")


def build():
    # Создаем папку dist если её нет
    os.makedirs(dist_path, exist_ok=True)

    # Создаем version_info.txt
    with open(version_info_path, "w", encoding="utf-8") as f:
        f.write(version_template)

    print(f"Version file created at: {version_info_path}")

    # Запускаем PyInstaller
    print("Running PyInstaller with command:")
    print(" ".join(command))
    PyInstaller.__main__.run(command)

    # Очистка временных файлов
    shutil.rmtree(os.path.join(dist_path, 'build_temp'), ignore_errors=True)
    if os.path.exists(version_info_path):
        os.unlink(version_info_path)
    if os.path.exists(f"{title}.spec"):
        os.unlink(f"{title}.spec")


if __name__ == "__main__":
    build()

    if run_exe:
        exe_path = os.path.join(dist_path, f"{title}.exe")
        if os.path.exists(exe_path):
            print(f"Starting {exe_path}")
            os.startfile(exe_path)
        else:
            print(f"Error: {exe_path} not found!")