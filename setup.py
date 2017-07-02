import sys
from cx_Freeze import setup, Executable

build_exe_options = {"packages": ["numpy"], "excludes": []}

base = None
if sys.platform == "win32":
    base = "Win32GUI"

setup(name = "bomberoni",
    version = "0.1",
    description = "Bomberoni",
    options = {"build_exe": build_exe_options},
    executables = [Executable("bomberoni.py", base=base)])
