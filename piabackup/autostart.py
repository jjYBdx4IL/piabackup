# encoding: utf-8
import ctypes
import logging
import os
import sys
import winreg
from ctypes import wintypes
from tkinter import messagebox

import piabackup.common as common


def is_running_in_sandbox():
    try:
        kernel32 = ctypes.windll.kernel32
        length = wintypes.DWORD(0)
        return kernel32.GetCurrentPackageFullName(ctypes.byref(length), None) != 15700
    except Exception:
        return False

def is_auto_start():
    try:
        if is_running_in_sandbox():
            return True # Managed by AppX Manifest
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, common.APPNAME)
        winreg.CloseKey(key)
        return True
    except OSError:
        return False

def toggle_auto_start(enable):
    if is_running_in_sandbox():
        try:
            os.startfile("ms-settings:startupapps")
        except Exception as e:
            logging.error(f"Failed to open startup settings: {e}")
        return

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            if getattr(sys, 'frozen', False):
                command = f'"{sys.executable}"'
            else:
                python_exe = sys.executable.replace("python.exe", "pythonw.exe") if "python.exe" in sys.executable else sys.executable
                command = f'"{python_exe}" "{os.path.abspath(__file__)}"'
            winreg.SetValueEx(key, common.APPNAME, 0, winreg.REG_SZ, command)
            logging.info("Autostart enabled")
        else:
            try:
                winreg.DeleteValue(key, common.APPNAME)
                logging.info("Autostart disabled")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        logging.error(f"Failed to toggle autostart: {e}")
        messagebox.showerror("Error", f"Failed to update registry: {e}")
