# encoding: utf-8
import ctypes
import logging


class SleepInhibitor:
    def __init__(self):
        self._nest_count = 0

    def __enter__(self):
        if self._nest_count == 0:
            logging.debug("enabling prevent_sleep_windows")
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        self._nest_count += 1

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._nest_count -= 1
        if self._nest_count <= 0:
            logging.debug("disabling prevent_sleep_windows")
            ctypes.windll.kernel32.SetThreadExecutionState(0)
            self._nest_count = 0
