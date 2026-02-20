#! /usr/bin/env python3
# encoding: utf-8
# @MAKEAPPX:AUTOSTART@
import logging
import os
import sys
import ctypes
import threading
import time
import tkinter as tk
from tkinter import messagebox

import keyring
import portalocker
import pystray
from PIL import Image, ImageDraw
from windows_toasts import Toast

import piabackup.common as common
from piabackup.backup_dir import BackupDir
from piabackup.config import Config
from piabackup.db import DB
from piabackup.disclaimer_window import DisclaimerWindow
from piabackup.password_dialog import PasswordDialog
from piabackup.settings_window import SettingsWindow
from piabackup.tools_installer import ToolsInstaller
from piabackup.update_checker import UpdateChecker
from piabackup.worker_thread import (AutoDiscoveryTask, BackupTask,
                                     RepoFullCheckTask, UpdateCheckTask,
                                     WorkerThread)
from ui.licenses_window import LicensesWindow
from ui.tkless import TkLess

# Global variables
tray_icon = None
app_lock_handle = None
lock_file_handle = None
settings_window = None
log_window = None
disclaimer_window = None
licenses_window = None
scheduler_timer = None
last_error_check_time = 0

def acquire_lock():
    global app_lock_handle, lock_file_handle
    kernel32 = ctypes.windll.kernel32
    name = f"Global\\{common.APPNAME}_SingleInstance"
    
    app_lock_handle = kernel32.CreateSemaphoreW(None, 1, 1, name)
    if not app_lock_handle:
        name = f"Local\\{common.APPNAME}_SingleInstance"
        app_lock_handle = kernel32.CreateSemaphoreW(None, 1, 1, name)

    if not app_lock_handle:
        return False

    if ctypes.get_last_error() == 183: # ERROR_ALREADY_EXISTS
        return False
        
    try:
        lock_file_handle = open(common.LOCK_FILE_PATH, 'a')
        portalocker.lock(lock_file_handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
    except portalocker.LockException:
        return False

    return True

def create_image():
    # Create a simple icon
    width = 64
    height = 64
    image = Image.new('RGB', (width, height), color=(73, 109, 137))
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=(255, 255, 255))
    return image

def quit_app():
    logging.info("user requested app termination")
    common.shutdown_requested = True
    WorkerThread.shutdown()
    WorkerThread.waitjoin()
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
        settings_window = SettingsWindow(root, on_trigger_run=lambda: root.after(0, check_scheduler))
    else:
        def on_accept():
            global settings_window
            settings_window = SettingsWindow(root, on_trigger_run=lambda: root.after(0, check_scheduler))
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
                logging.error(f"Failed to read license for {name}: {e}")

    licenses_window = LicensesWindow(root, extra_licenses=extra_licenses)

def check_scheduler():
    global scheduler_timer, last_error_check_time
    if scheduler_timer:
        if root: root.after_cancel(scheduler_timer)
        scheduler_timer = None

    now = time.time()
    next_wake_time = now + 3600

    errors = []

    try:
        cfg = Config()

        env = os.environ.copy()
        ready = False
        if cfg.repo:
            password = keyring.get_password(common.APPNAME, "repository")
            if not password:
                def open_pwd_dialog(args):
                    if root: root.after(0, lambda: PasswordDialog(root))
                toast = Toast()
                toast.text_fields = ["Backup Failed", "Repository password is not set. Click to set it."]
                toast.on_activated = open_pwd_dialog
                common.wintoaster.show_toast(toast)
                logging.warning("Backup skipped: Password not set")
                next_wake_time = time.time() + 300
            else:
                env["RESTIC_REPOSITORY"] = cfg.repo
                env["RESTIC_PASSWORD"] = password
                ready = True
        elif "RESTIC_REPOSITORY" in os.environ:
            ready = True

        if ready:
            # 1. Backups
            for entry in BackupDir.fetch_enabled_backup_rows():
                if entry.error:
                    errors.append(f"{entry.path}: {entry.error}")
                task_id = f"backup_{entry.id}"
                if entry.next_run <= now:
                    class ScheduledBackupTask(BackupTask):
                        def on_final(self):
                            super().on_final()
                            if root: root.after(0, check_scheduler)
                    WorkerThread.submit_task(ScheduledBackupTask(env, entry, cfg, task_id=task_id))
                else:
                    if entry.next_run < next_wake_time:
                        next_wake_time = entry.next_run

            # 2. Full Repo Check
            with common.db_conn as conn:
                last_full_check = float(conn.execute("SELECT value FROM status WHERE key = 'last_full_check'").fetchone()[0])
                full_check_frequency = float(conn.execute("SELECT value FROM config WHERE key = 'full_check_frequency'").fetchone()[0])
                next_check = last_full_check + full_check_frequency

            if now > last_full_check + (2 * cfg.full_check_frequency):
                last_run_str = time.ctime(last_full_check) if last_full_check > 0 else "Never"
                errors.append(f"Full check is overdue (Last run: {last_run_str})")

            if next_check <= now:
                row = common.db_conn.execute("SELECT value FROM status WHERE key = 'last_full_check_segment'").fetchone()
                last_full_check_segment = int(row[0]) if row else 0
                
                segment_to_run = None
                if last_full_check_segment >= 0 and last_full_check_segment < common.FULL_CHECK_SEGMENTS:
                    segment_to_run = last_full_check_segment + 1
                elif DB.full_check_due_in() < 0:
                    segment_to_run = 0
                
                if segment_to_run is not None:
                    class ScheduledCheckTask(RepoFullCheckTask):
                        def on_final(self):
                            if root: root.after(0, check_scheduler)

                    WorkerThread.submit_task(ScheduledCheckTask(env, cfg, segment_to_run, task_id="full_repo_check"))
                else:
                    if next_check < next_wake_time:
                        next_wake_time = next_check

            # 3. error toast
            if now >= last_error_check_time + cfg.error_check_frequency:
                last_error_check_time = now
                if errors:
                    toast = Toast()
                    toast.text_fields = ["Backup Errors Detected", "\n".join(errors)[:200]]
                    common.wintoaster.show_toast(toast)
            next_check = last_error_check_time + cfg.error_check_frequency
            if next_check < next_wake_time:
                next_wake_time = next_check

            # 4. Auto Discovery
            if cfg.auto_discovery:
                with common.db_conn as conn:
                    cursor = conn.execute("SELECT value FROM status WHERE key = 'last_auto_discovery'")
                    row = cursor.fetchone()
                    last_auto_discovery = float(row[0]) if row else 0
                
                next_auto_disc = last_auto_discovery + 86400
                if now > next_auto_disc:
                     WorkerThread.submit_task(AutoDiscoveryTask(task_id="auto_discovery"))
                elif next_auto_disc < next_wake_time:
                     next_wake_time = next_auto_disc

            # 5. Update Check
            if cfg.update_check_enabled:
                uc = UpdateChecker()
                
                check_ival = cfg.update_check_frequency if uc.cached_version != "ERROR" else common.MIN_UPDATE_CHECK_IVAL
                next_check = uc.last_check + check_ival
                
                if now > next_check:
                    WorkerThread.submit_task(UpdateCheckTask(task_id="update_check"))
                elif next_check < next_wake_time:
                    next_wake_time = next_check
                
                uc.show_toast_if_needed(cfg.update_check_toast_interval)

                if uc.cached_version and uc.cached_version != "ERROR":
                    next_toast = uc.last_toast + cfg.update_check_toast_interval
                    if next_toast < next_wake_time:
                        next_wake_time = next_toast

    except Exception as e:
        logging.exception(f"Scheduler error: {e}")
        next_wake_time = time.time() + 60

    delay = int((next_wake_time - time.time()) * 1000)
    if delay < 1000: delay = 1000
    
    if root:
        scheduler_timer = root.after(delay, check_scheduler)
            
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

        DB.init_db()

        installer = ToolsInstaller(common.BIN_DL_DIR, common.APPNAME)
        tools_config = get_tools_info()
        installer.check_and_install_tools(tools_config)

        if not common.IS_ADMIN:
            toast = Toast()
            toast.text_fields = ["Privilege Warning", "Running without admin privileges.\nVSS snapshots will not be available."]
            common.wintoaster.show_toast(toast)
            logging.warning("Running without admin privileges.")

        root = tk.Tk()
        common.root = root
        root.withdraw()

        if common.IS_DEBUGGER_PRESENT:
            root.after(0, open_settings)
            root.after(3, check_scheduler)
        else:
            root.after(5000, check_scheduler)
        
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
        logging.error(f"Error: {e}")
        raise
    finally:
        if common.db_conn:
            common.db_conn.close()
        logging.info(f"{common.APPNAME} exiting")
