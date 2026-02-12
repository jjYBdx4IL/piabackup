# encoding: utf-8
import logging
import shutil
import threading
import time
import queue
from windows_toasts import Toast
import keyring
import sqlite3
import os
from tkinter import messagebox
import piabackup.common as common
from piabackup.backup_dir import BackupDir
from piabackup.config import Config
from piabackup.restic import Restic
from piabackup.sleep_inhibitor import SleepInhibitor
from piabackup.password_dialog import PasswordDialog
from piabackup.fast_scan import FastScan

class WorkerThread(threading.Thread):
    task_queue = queue.Queue()
    result_queue = queue.Queue()

    @staticmethod
    def submit_task(func, *args):
        WorkerThread.task_queue.put((func, args))
        WorkerThread.start_worker_thread()

    @staticmethod
    def get_result():
        try:
            return WorkerThread.result_queue.get_nowait()
        except queue.Empty:
            return None

    def __init__(self, name):
        super().__init__(daemon=True, name=name)

    def run(self):
        common.log.debug("hello")
        cfg = Config()
        
        conn = sqlite3.connect(common.DB_PATH)

        env = os.environ.copy()
        if cfg.repo:
            password = keyring.get_password(common.APPNAME, "repository")
            if not password:
                def open_pwd_dialog(args):
                    common.root.after(0, lambda: PasswordDialog(common.root))
                toast = Toast()
                toast.text_fields = ["Backup Failed", "Repository password is not set. Click to set it."]
                toast.on_activated = open_pwd_dialog
                common.wintoaster.show_toast(toast)
                common.log.warning("Backup skipped: Password not set")
                return
            env["RESTIC_REPOSITORY"] = cfg.repo
            env["RESTIC_PASSWORD"] = password
        elif "RESTIC_REPOSITORY" not in os.environ:
            common.root.after(0, lambda: messagebox.showerror("Error", "Repository not configured"))
            return

        with SleepInhibitor():
            self.backup_loop(conn, env, cfg)
        common.log.debug("bye")

    def run_one_backup(self, conn:sqlite3.Connection, env, cfg:Config) -> bool:
        restic = Restic()

        entry = BackupDir.fetch_overdue_backup_row(conn)
        
        if entry is None:
            return False

        try:
            entry.error = ""
            needs_prune = cfg.prune_enabled and (time.time() >= entry.last_prune + cfg.prune_frequency)
            dir_exists = self.process_backup_dir(entry, env, cfg.no_lock, needs_prune and cfg.bitrot_detection)
            if common.shutdown_requested: return True
            if dir_exists and needs_prune:
                if cfg.bitrot_detection:
                    common.log.info(f"Checking for bitrot for {entry.path}...")
                    entry.bitrot_snap = restic.check_bitrot(cfg, env, entry.get_tag(), entry.bitrot_snap)
                if common.shutdown_requested: return True
                common.log.info(f"Pruning repository for {entry.path}...")
                restic.forget_some(entry.get_tag(), env)
                entry.last_prune = time.time()
        except Exception as ex:
            common.log.error(f"Backup failed for {entry.path}: {ex}")
            entry.error = str(ex)

        with conn:
            entry.save_backup_result(conn)

        return True

    def process_tasks(self):
        did_work = False
        while True:
            try:
                func, args = self.task_queue.get_nowait()
                try:
                    res = func(*args)
                    self.result_queue.put(("success", res))
                except Exception as e:
                    self.result_queue.put(("error", e))
                did_work = True
            except queue.Empty:
                break
        return did_work

    def backup_loop(self, conn:sqlite3.Connection, env, cfg:Config):
        while not common.shutdown_requested:
            if self.process_tasks():
                continue
            if self.run_one_backup(conn, env, cfg): # prioritize running backups without delay
                continue
            if self.run_full_repo_check(conn, env, cfg):
                continue
            break # nothing to do -> shut down the worker thread (implicitly refreshes the config from db)

    def run_full_repo_check(self, conn:sqlite3.Connection, env, cfg:Config) -> bool:
        restic = Restic()
        try:
            last_full_check = float(conn.execute("SELECT value FROM status WHERE key = 'last_full_check'").fetchone()[0])
            
            if time.time() >= last_full_check + cfg.full_check_frequency:
                common.log.info("Full check is due, running...")
                last_full_check_segment = int(conn.execute("SELECT value FROM status WHERE key = 'last_full_check_segment'").fetchone()[0])
                if last_full_check_segment >= common.FULL_CHECK_SEGMENTS:
                    with conn:
                        conn.execute("UPDATE status SET value = ? WHERE key = 'last_full_check_segment'", ("0",))
                        conn.execute("UPDATE status SET value = ? WHERE key = 'last_full_check'", (time.time(),))
                    return False # we done

                if last_full_check_segment == 0:
                    if common.RESTIC_CACHE_DIR.exists():
                        shutil.rmtree(common.RESTIC_CACHE_DIR)
                        common.log.info("Restic cache cleared")
                
                if common.shutdown_requested: return True # not done

                last_full_check_segment += 1
                restic.run_check_cmd(env, cfg.no_lock, last_full_check_segment)
                with conn:
                    conn.execute("INSERT OR REPLACE INTO status (key, value) VALUES (?, ?)", ("last_full_check_segment", str(last_full_check_segment)))
                return True
        except Exception as e:
            common.log.error(f"Full check failed: {e}")
        return False

    def process_backup_dir(self, entry:BackupDir, env, no_lock, full_check=False) -> bool:
        if not entry.path.exists():
            if entry.enabled == 'yes':
                raise Exception("Directory not found")
            # we can risk wasting a bit of time on a pre-scan the next time the directory appears again
            if entry.fastscan_fingerprint == "0":
                entry.fastscan_fingerprint = "1"
            return False

        should_run = True
        if entry.fastscan_fingerprint == "0":
            should_run = True
        else:
            try:
                fp = FastScan.directory_fingerprint(entry.path, limit=common.FILE_SCAN_LIMIT)
                
                if fp is None:
                    entry.fastscan_fingerprint = "0"
                    should_run = True
                    common.log.info(f"Disabling pre-scan for '{entry.path}'.")
                else:
                    if fp != entry.fastscan_fingerprint:
                        should_run = True
                        entry.fastscan_fingerprint = fp
                    else:
                        should_run = False
            except Exception as e:
                common.log.error(f"Scan failed for {entry.path}: {e}")
                should_run = True
        
        if full_check:
            should_run = True

        if not should_run:
            common.log.info(f"Skipping {entry.path}: No changes detected during pre-scan.")
            return True

        restic = Restic()
        entry.summary = restic.run_backup_cmd(entry.path, env, full_check, no_lock)
        return True

    @staticmethod
    def start_worker_thread():
        global worker_thread
        if worker_thread and worker_thread.is_alive():
            return
        worker_thread = WorkerThread("WorkerThread")
        worker_thread.start()
        logging.info("Worker thread started.")
