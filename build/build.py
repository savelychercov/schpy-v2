"""
Создает .exe файл в папке build
"""

import datetime
import os
import shutil

import PyInstaller.__main__

from src import db

dist_path = ""
title = "SchPy"
start_file = "../src/window.py"
icon_name = "icon.ico"
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

version_template = f"""
VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=({major_version}, {minor_version}, {patch_version}, {build_number}),
        prodvers=({major_version}, {minor_version}, {patch_version}, {build_number}),
        mask=0x3f,
        flags={"0x1" if debug else "0x0"},
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date={datetime.datetime.now().year, datetime.datetime.now().month}
    ),
    kids=[
        StringFileInfo([
            StringTable(
                u'040904E4',
                [
                    StringStruct(u'CompanyName', u'{company_name}'),
                    StringStruct(u'FileDescription', u'{description}'),
                    StringStruct(u'FileVersion', u'{f"{major_version}.{minor_version}.{patch_version}.{build_number}"}'),
                    StringStruct(u'LegalCopyright', u'© {datetime.datetime.now().year} {company_name}'),
                    StringStruct(u'ProductName', u'AppName'),
                    StringStruct(u'ProductVersion', u'1.0.0.0'),
                ]
            )
        ]),
        VarFileInfo([VarStruct(u'Translation', [1033, 1252])])
    ]
)
"""


dirs = []

files = [
    "icon.ico",
    "schedule_maker.py",
    "best_of.py",
    "db.py",
    "MainWindow.css",
    "InputDataDialog.css",
    "ScheduleGeneratorDialog.css",
    "ErrorDialog.css",
]

command = [
    start_file,
    "--noconfirm",
    "--onefile",
    f"--icon={icon_name}",
    f"--name={title}",
    "--clean",
    f"--distpath={dist_path}",
    f"--version-file={dist_path}/version_info.txt",
]

if no_console:
    command.append("--noconsole")

for d in dirs:
    command.append(f"--add-data={d};{d}/")

for filename in files:
    filename = os.path.join(current_directory, filename)
    print("Adding file:", filename)
    command.append(f"--add-data={filename};.")


def build():
    shutil.rmtree(dist_path, ignore_errors=True)
    os.makedirs(dist_path, exist_ok=True)
    with open(f"{dist_path}/version_info.txt", "w", encoding="utf-8") as f:
        f.write(version_template)

    PyInstaller.__main__.run(command)

    shutil.rmtree(f"{dist_path}/{title}")
    os.unlink(f"{title}.spec")
    os.unlink(f"{dist_path}/version_info.txt")


if __name__ == "__main__":
    build()

    if run_exe:
        os.startfile(f"{dist_path}\\{title}.exe")
