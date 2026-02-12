#! /usr/bin/env python3
# encoding: utf-8
# @MAKEAPPX:AUTOSTART@
import os
import sys
import logging
import threading
import time
import tkinter as tk
from tkinter import messagebox
import sqlite3
import portalocker
import pystray
from PIL import Image, ImageDraw
from windows_toasts import Toast
import piabackup.common as common
from piabackup.backup_dir import BackupDir
from piabackup.DefaultDirsScanner import DefaultDirsScanner
from piabackup.db import DB
from piabackup.config import Config
from piabackup.settings_window import SettingsWindow
from ui.tkless import TkLess
from ui.licenses_window import LicensesWindow
from piabackup.tools_installer import ToolsInstaller
from piabackup.worker_thread import WorkerThread
from piabackup.disclaimer_window import DisclaimerWindow
from piabackup.update_checker import UpdateChecker

# Global variables
tray_icon = None
lock_file_handle = None
settings_window = None
log_window = None
disclaimer_window = None
licenses_window = None

def acquire_lock():
    global lock_file_handle
    try:
        lock_file_handle = open(common.LOCK_FILE_PATH, 'a')
        portalocker.lock(lock_file_handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        return True
    except portalocker.LockException:
        return False

def create_image():
    # Create a simple icon
    width = 64
    height = 64
    image = Image.new('RGB', (width, height), color=(73, 109, 137))
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=(255, 255, 255))
    return image

def quit_app():
    global shutdown_requested
    shutdown_requested = True
    logging.info("user requested app termination")
    if common.worker_thread and common.worker_thread.is_alive():
        logging.info("waiting for worker thread to finish...")
        common.worker_thread.join()
        logging.info("worker thread finished")
    if tray_icon: tray_icon.stop()
    root.destroy()

def open_settings():
    global settings_window, disclaimer_window
    if settings_window and settings_window.winfo_exists():
        settings_window.lift()
        settings_window.focus_force()
        return

    if disclaimer_window and disclaimer_window.winfo_exists():
        disclaimer_window.lift()
        disclaimer_window.focus_force()
        return

    cfg = Config()
    if cfg.disclaimer_accepted:
        settings_window = SettingsWindow(root)
    else:
        def on_accept():
            global settings_window
            settings_window = SettingsWindow(root)
        disclaimer_window = DisclaimerWindow(root, on_accept, quit_app)

def open_log():
    global log_window
    if log_window and log_window.root.winfo_exists():
        log_window.root.lift()
        log_window.root.focus_force()
        return
    log_window = TkLess(root, common.LOG_FILE_PATH)

def open_licenses():
    global licenses_window
    if licenses_window and licenses_window.winfo_exists():
        licenses_window.lift()
        licenses_window.focus_force()
        return
    
    extra_licenses = []
    tools_info = get_tools_info()
    
    for name, info in tools_info.items():
        path = os.path.join(common.BIN_DL_DIR, info["license_filename"])
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    extra_licenses.append({
                        "Name": name,
                        "Version": "Installed",
                        "License": "See Text",
                        "LicenseText": f.read(),
                        "URL": info["project_url"],
                        "Author": f"{name} Team"
                    })
            except Exception as e:
                common.log.error(f"Failed to read license for {name}: {e}")

    licenses_window = LicensesWindow(root, extra_licenses=extra_licenses)

def check_scheduler():
    if root:
        root.after(300000, check_scheduler)

    if common.worker_thread and common.worker_thread.is_alive():
        pass
    else:
        # Check for overdue
        try:
            overdue = False
            with sqlite3.connect(common.DB_PATH) as conn:
                row = BackupDir.fetch_overdue_backup_row(conn)
                if row:
                    overdue = True
                else:
                    if DB.is_full_check_due(conn):
                        overdue = True
            if overdue:
                WorkerThread.start_worker_thread()
        except Exception as e:
            common.log.error(f"Scheduler error: {e}")
            
def check_errors():
    if root:
        try:
            cfg = Config()
            ival = cfg.error_check_frequency * 1000
            if ival < 60000: ival = 60000
            root.after(ival, check_errors)
            
            with sqlite3.connect(common.DB_PATH) as conn:
                rows = BackupDir.fetch_enabled_backup_rows(conn)
                errors = []
                for row in rows:
                    if row.error:
                        errors.append(f"{row.path}: {row.error}")
                
                last_full_check = float(conn.execute("SELECT value FROM status WHERE key = 'last_full_check'").fetchone()[0])
                if time.time() > last_full_check + (2 * cfg.full_check_frequency):
                    last_run_str = time.ctime(last_full_check) if last_full_check > 0 else "Never"
                    errors.append(f"Full check is overdue (Last run: {last_run_str})")
                
                if errors:
                    toast = Toast()
                    toast.text_fields = ["Backup Errors Detected", "\n".join(errors)[:200]]
                    common.wintoaster.show_toast(toast)
        except Exception as e:
            common.log.error(f"Error check failed: {e}")
            if root: root.after(60000, check_errors)

def check_auto_discovery():
    if root:
        # Check every hour
        root.after(3600000, check_auto_discovery)
        
        try:
            cfg = Config()
            if not cfg.auto_discovery:
                return

            with sqlite3.connect(common.DB_PATH) as conn:
                cursor = conn.execute("SELECT value FROM status WHERE key = 'last_auto_discovery'")
                row = cursor.fetchone()
                last_run = float(row[0]) if row else 0
                
                if time.time() - last_run < 86400:
                    return

                common.log.info("Running auto-discovery...")
                scanner = DefaultDirsScanner()
                found = scanner.scan()
                
                if found:
                    existing_rows = conn.execute("SELECT path FROM backup_dirs").fetchall()
                    existing_paths = {r[0].lower() for r in existing_rows}
                    
                    added_count = 0
                    for p in found:
                        if p.lower() not in existing_paths:
                            bd = BackupDir(None, p, enabled='auto')
                            bd.save_ui(conn)
                            added_count += 1
                            common.log.info(f"Auto-discovery added: {p}")
                    
                    if added_count > 0:
                        toast = Toast()
                        toast.text_fields = ["New Backup Paths Detected", f"Added {added_count} new paths."]
                        common.wintoaster.show_toast(toast)

                conn.execute("INSERT OR REPLACE INTO status (key, value) VALUES (?, ?)", ("last_auto_discovery", str(time.time())))
        except Exception as e:
            common.log.error(f"Auto-discovery failed: {e}")

def check_app_updates():
    UpdateChecker.background_check_loop(root)

def get_tools_info():
    return {
        "restic": {
            "ver": "restic 0.18.1 compiled with go1.25.1 on windows/amd64",
            "url": "https://github.com/restic/restic/releases/download/v0.18.1/restic_0.18.1_windows_amd64.zip",
            "zip_path": "restic_0.18.1_windows_amd64.exe",
            "exe": "restic.exe",
            "sha256": "0c1a713440578cb400d2e76208feb24f1b339426b075a21f73b6b2132692515d",
            "license_url": "https://raw.githubusercontent.com/restic/restic/refs/heads/master/LICENSE",
            "license_filename": "restic_LICENSE.txt",
            "project_url": "https://github.com/restic/restic"
        },
        "rclone": {
            "ver": "rclone v1.73.0",
            "url": "https://github.com/rclone/rclone/releases/download/v1.73.0/rclone-v1.73.0-windows-amd64.zip",
            "zip_path": "rclone-v1.73.0-windows-amd64/rclone.exe",
            "exe": "rclone.exe",
            "sha256": "14e1c40f34ec18532e832c228231338bd182817af6f6529a402474c69acabe0b",
            "license_url": "https://raw.githubusercontent.com/rclone/rclone/refs/heads/master/COPYING",
            "license_filename": "rclone_LICENSE.txt",
            "project_url": "https://rclone.org/"
        }
    }

if __name__ == "__main__":
    try:
        common.xxinit()

        if not acquire_lock():
            messagebox.showerror(common.APPNAME, "Another instance is already running, exit(1).")
            sys.exit(1)

        installer = ToolsInstaller(common.BIN_DL_DIR, common.APPNAME)
        tools_config = get_tools_info()
        installer.check_and_install_tools(tools_config)

        DB.init_db()

        if not common.IS_ADMIN:
            toast = Toast()
            toast.text_fields = ["Privilege Warning", "Running without admin privileges.\nVSS snapshots will not be available."]
            common.wintoaster.show_toast(toast)
            common.log.warning("Running without admin privileges.")

        root = tk.Tk()
        root.withdraw()

        if common.IS_DEBUGGER_PRESENT:
            root.after(0, open_settings)
            root.after(3, check_scheduler)
            root.after(5000, check_errors)
            root.after(10000, check_auto_discovery)
            root.after(15000, check_app_updates)
        else:
            root.after(5000, check_scheduler)
            root.after(10000, check_errors)
            root.after(15000, check_auto_discovery)
            root.after(20000, check_app_updates)
        
        menu = pystray.Menu(
            pystray.MenuItem("Run overdue backups now", lambda i, it: root.after(0, WorkerThread.start_worker_thread)),
            pystray.MenuItem("Settings...", lambda i, it: root.after(0, open_settings)),
            pystray.MenuItem("Open Log", lambda i, it: root.after(0, open_log)),
            pystray.MenuItem("Licenses", lambda i, it: root.after(0, open_licenses)),
            pystray.MenuItem("Exit", lambda i, it: root.after(0, quit_app))
        )
        tray_icon = pystray.Icon(common.APPNAME, create_image(), common.APPNAME, menu)
        threading.Thread(target=tray_icon.run, daemon=True, name="IconThread").start()
        root.mainloop()
    except Exception as e:
        common.log.error(f"Error: {e}")
        raise
    finally:
        common.log.info(f"{common.APPNAME} exiting")
