# encoding: utf-8
import ctypes
import logging
import os
import shlex
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path
from tkinter import Tk

from windows_toasts import WindowsToaster

APPNAME = "piabackup"
APP_VERSION = "0.8.0.0"
APP_UPDATE_CHECK_URL = "https://api.github.com/repos/jjYBdx4IL/piabackup/releases/latest"

LAPPDATA_PATH = Path(os.environ.get('LOCALAPPDATA', os.path.join(os.path.expanduser('~'), 'AppData', 'Local')))
LOG_DIR_PATH = LAPPDATA_PATH / 'log'

LOG_FILE_PATH = LOG_DIR_PATH / f'{APPNAME}.log'

CFG_DIR_PATH = LAPPDATA_PATH / 'py_apps' / APPNAME
LOCK_FILE_PATH = CFG_DIR_PATH / 'lock'
DB_PATH = CFG_DIR_PATH / 'sqlite.db'

BIN_DL_DIR = CFG_DIR_PATH / 'dl'

MIN_FREQUENCY = 60
DEFAULT_FREQ = 86400
DEFAULT_FILE_SCAN_LIMIT = 200000

DEFAULT_CHECK_IVAL = 86400 * 7 # perform an intense check every N days 
DEFAULT_PRUNE_IVAL = 86400 * 7
DEFAULT_ERROR_CHECK_IVAL = 1800
DEFAULT_UPDATE_CHECK_IVAL = 86400 * 7
DEFAULT_UPDATE_TOAST_IVAL = 3600 * 12
MIN_UPDATE_CHECK_IVAL = 3600 * 3

FULL_CHECK_SEGMENTS = 100

RESTIC_CACHE_DIR = LAPPDATA_PATH / "restic"

IS_ADMIN = False
try:
    IS_ADMIN = ctypes.windll.shell32.IsUserAnAdmin()
except:
    pass

IS_DEBUGGER_PRESENT = sys.gettrace() is not None or os.environ.get('VSCODE_PID') or 'debugpy' in sys.modules

root:Tk.Tk = None
wintoaster = WindowsToaster(APPNAME)
shutdown_requested:bool = False
db_conn:sqlite3.Connection = None

def center_window(win, width, height):
    screen_width = win.winfo_screenwidth()
    screen_height = win.winfo_screenheight()
    x = (screen_width - width) // 2
    y = (screen_height - height) // 3
    win.geometry(f'{width}x{height}+{x}+{y}')

def setup_logging():
    console_log_level = logging.INFO if not IS_DEBUGGER_PRESENT else logging.DEBUG
    file_handler = logging.FileHandler(LOG_FILE_PATH, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    logging.basicConfig(
        level=console_log_level,
        format='%(asctime)s [%(process)5d] [%(threadName)s] %(levelname).3s: %(message)s',
        handlers=[
            file_handler,
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.getLogger("PIL").setLevel(logging.WARNING)

def xxinit():
    LOG_DIR_PATH.mkdir(parents=False, exist_ok=True)
    CFG_DIR_PATH.mkdir(parents=True, exist_ok=True)
    BIN_DL_DIR.mkdir(parents=True, exist_ok=True)
    
    setup_logging()
    logging.info(f"{APPNAME} started")

    os.environ["PATH"] = str(BIN_DL_DIR) + os.pathsep + os.environ["PATH"]
    logging.debug(f"Initialized paths: added '{BIN_DL_DIR}' to PATH")

def remove_readonly(func, path, exc_info):
    try:
        if IS_DEBUGGER_PRESENT:
            logging.debug(f"remove_readonly: {func} {path} {exc_info}")
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        logging.exception("")
        raise
    except:
        logging.exception("")
        raise

def quote_command(cmd_list:list[str]):
    """
    Returns a shell-escaped string version of the command list
    appropriate for the current operating system.
    """
    if sys.platform == "win32":
        # Windows cmd.exe style quoting
        return subprocess.list2cmdline(cmd_list)
    else:
        # POSIX (Linux/macOS) shell style quoting
        return shlex.join(cmd_list)
    