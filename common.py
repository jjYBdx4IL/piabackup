# encoding: utf-8
import ctypes
import logging
import os
import shlex
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
import tkinter as Tk

from windows_toasts import WindowsToaster

from piabackup import APPNAME
import ui.tools

LAPPDATA_PATH = Path(os.environ.get('LOCALAPPDATA', os.path.join(os.path.expanduser('~'), 'AppData', 'Local')))
LOG_DIR_PATH = LAPPDATA_PATH / 'log'
LOG_DIR_PATH.mkdir(parents=True, exist_ok=True)

LOG_FILE_PATH = LOG_DIR_PATH / f'{APPNAME}.log'

CFG_DIR_PATH = LAPPDATA_PATH / 'py_apps' / APPNAME
CFG_DIR_PATH.mkdir(parents=True, exist_ok=True)
LOCK_FILE_PATH = CFG_DIR_PATH / 'lock'
DB_PATH = CFG_DIR_PATH / 'sqlite.db'

BIN_DL_DIR = CFG_DIR_PATH / 'dl'
BIN_DL_DIR.mkdir(parents=True, exist_ok=True)

MIN_FREQUENCY = 60
DEFAULT_FREQ = 86400

DEFAULT_CHECK_IVAL = 86400 * 7 # perform an intense check every N days 
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



root:Tk.Tk|None = None
wintoaster = WindowsToaster(APPNAME)
shutdown_requested:bool = False

def setup_logging():
    console_log_level = logging.INFO if not ui.tools.IS_DEBUGGER_PRESENT else logging.DEBUG
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

setup_logging()
logging.info(f"{APPNAME} started")

os.environ["PATH"] = str(BIN_DL_DIR) + os.pathsep + os.environ["PATH"]
logging.debug(f"Initialized paths: added '{BIN_DL_DIR}' to PATH")

db_conn:sqlite3.Connection = sqlite3.connect(DB_PATH)

def remove_readonly(func, path, exc_info):
    try:
        if ui.tools.IS_DEBUGGER_PRESENT:
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

def format_restic_path(path: Path):
    # Transform C:\Users\work to /C/Users/work
    drive = path.drive
    if drive:
        return "/" + drive.replace(":", "") + path.as_posix().replace(drive, "")
    return path.as_posix()

@contextmanager
def handle_iexclude_file(iexclude: str|None, backup_path: Path, is_rewrite: bool = False):
    if not iexclude:
        yield None
        return

    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8', suffix=".txt") as tmp:
        absolute_exclusions = []
        if sys.platform == "win32" and is_rewrite:
            for line in iexclude.splitlines():
                line = line.strip()
                if line:
                    absolute_exclusions.append(format_restic_path(backup_path.joinpath(line.lstrip('/\\'))))
        else:
            for line in iexclude.splitlines():
                line = line.strip()
                if line:
                    absolute_exclusions.append(backup_path.joinpath(line.lstrip('/\\')).as_posix())

        if ui.tools.IS_DEBUGGER_PRESENT:
            logging.debug("iexclude file=" + "\n".join(absolute_exclusions))
        
        tmp.write("\n".join(absolute_exclusions))
        tmp_path = tmp.name

    try:
        yield tmp_path
    finally:
        os.remove(tmp_path)

def get_system_sleep_timeout():
    """
    Queries Windows for the current sleep (standby) timeouts.
    Returns a tuple: (ac_timeout_seconds, dc_timeout_seconds)
    """
    # powercfg /q queries the active scheme (SCHEME_CURRENT) 
    # for the Sleep subgroup (SUB_SLEEP) and Standby Idle setting (STANDBYIDLE)
    cmd = "powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE"
    
    # Run the command and capture the output
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    
    ac_timeout = 0
    dc_timeout = 0
    
    # Parse the output line by line to find the hex values
    for line in result.stdout.splitlines():
        if "Current AC Power Setting Index" in line:
            # Extract the hex value at the end of the line and convert to integer
            hex_val = line.split(":")[-1].strip()
            ac_timeout = int(hex_val, 16)
            
        elif "Current DC Power Setting Index" in line:
            hex_val = line.split(":")[-1].strip()
            dc_timeout = int(hex_val, 16)
        
    timeo = ac_timeout
    if timeo <= 0 or dc_timeout < timeo and dc_timeout > 0:
        timeo = dc_timeout
    timeo = timeo * 0.7
    if timeo <= 0:
        timeo = 300
    return timeo
INACTIVITY_TIMEOUT = get_system_sleep_timeout()
logging.info(f"INACTIVITY_TIMEOUT={INACTIVITY_TIMEOUT}")


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_ulong)
    ]

def get_idle_duration_seconds():
    lastInputInfo = LASTINPUTINFO()
    lastInputInfo.cbSize = ctypes.sizeof(lastInputInfo)
    
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lastInputInfo)):
        millis_since_boot = ctypes.windll.kernel32.GetTickCount()
        millis_since_last_input = millis_since_boot - lastInputInfo.dwTime
        return millis_since_last_input / 1000.0
    else:
        return 0.0
    
system_suspended:bool = False
system_last_resumed:int = 0
SYSTEM_SUSPEND_DELAY:int = 300
def recently_suspended() -> bool:
    if system_suspended: # avoid starting new tasks when going into standby
        return True
    if time.time() < system_last_resumed + SYSTEM_SUSPEND_DELAY:
        return True
    return False

ASSETS_DIR = Path(__file__).parent

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # pyinstaller --one-dir --add-data xyz:assets
    ASSETS_DIR = Path(sys._MEIPASS) / 'assets' # type: ignore

