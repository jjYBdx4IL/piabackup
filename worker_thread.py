# encoding: utf-8
import json
import logging
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import PurePosixPath

from windows_toasts import Toast

import piabackup.common as common
from piabackup.backup_dir import BackupDir
from piabackup.default_dirs_scanner import DefaultDirsScanner
from piabackup.fast_scan import FastScan
from piabackup.restic import Restic
from piabackup.sleep_inhibitor import SleepInhibitor
from piabackup.update_checker import UpdateChecker


class WorkerTask:
    def __init__(self, **kwargs):
        tid = kwargs.get("task_id", None)
        self._task_id:str = str(tid) if tid is not None else None

    @property
    def task_id(self):
        return self._task_id

    # The on_* methods always run on the main UI thread where also the database connection lives.
    # Don't block the UI here!!
    def on_success(self, res):
        logging.info("Task completed.")

    def on_failure(self, e):
        logging.error(f"Task failed: {e}")

    def on_progress(self, *args):
        pass

    def on_final(self):
        pass

    # The run method is usually executed in parallel to the main UI thread, ie usually in the WorkerThread singleton.
    # Put long running stuff in here.
    def run(self):
        raise NotImplementedError()


class StreamingResticTask(WorkerTask):
    def __init__(self, env, no_lock, *args, iexclude=None, backup_path=None, **kwargs):
        super().__init__(**kwargs)
        self.env = env
        self.no_lock = no_lock
        self.command = list(args)
        self.iexclude = iexclude
        self.backup_path = backup_path

    def on_output(self, line):
        pass

    def run(self):
        cmd = ["restic"] + self.command
        if self.no_lock:
            cmd.append("--no-lock")

        with common.handle_iexclude_file(self.iexclude, self.backup_path, self.command[0] == 'rewrite') as iexclude_path:
            if iexclude_path:
                cmd.extend(["--iexclude-file", iexclude_path])
                #shutil.copyfile(iexclude_path, "dump.txt")

            logging.info(f"running: {common.quote_command(cmd)}")
            
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            p = subprocess.Popen(cmd, text=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=self.env, startupinfo=startupinfo, bufsize=1, universal_newlines=True)
            
            for line in p.stdout:
                logging.info(line.strip())
                self.on_output(line)
            
            stderr_output = ""
            for line in p.stderr:
                stderr_output += line
                logging.error(line.strip())
                self.on_output(line)

            rc = p.wait()
            if rc != 0:
                raise Exception(f"Command failed with exit code {rc}:\n{stderr_output}")
			
class ListSnapshotsTask(WorkerTask):
    def __init__(self, env, tag, no_lock, **kwargs):
        super().__init__(**kwargs)
        self.env = env
        self.tag = tag
        self.no_lock = no_lock

    def run(self):
        r = Restic()
        class MockConfig:
            def __init__(self, no_lock):
                self.no_lock = no_lock
        return r.list_snapshots(MockConfig(self.no_lock), self.env, self.tag)

class LsTask(WorkerTask):
    def __init__(self, env, snap_id, no_lock, **kwargs):
        super().__init__(**kwargs)
        self.env = env
        self.snap_id = snap_id
        self.no_lock = no_lock

    def run(self):
        r = Restic()
        return r.ls(self.env, self.snap_id, self.no_lock)

class FindTask(WorkerTask):
    def __init__(self, env, search_path, no_lock, **kwargs):
        super().__init__(**kwargs)
        self.env = env
        self.search_path = search_path
        self.no_lock = no_lock

    def run(self):
        r = Restic()
        return r.find(self.env, self.search_path, self.no_lock)

class RestoreTask(WorkerTask):
    def __init__(self, env, snap_id, target_dir, include_path, no_lock, flatten, backup_dir_parts, **kwargs):
        super().__init__(**kwargs)
        self.env = env
        self.snap_id = snap_id
        self.target_dir = target_dir
        self.include_path = include_path
        self.no_lock = no_lock
        self.flatten = flatten
        self.backup_dir_parts = backup_dir_parts

    def run(self):
        r = Restic()
        summary, errmsgs = r.restore(self.env, self.snap_id, self.target_dir, self.include_path, self.no_lock)

        if self.flatten:
            target_parts = []
            if self.include_path:
                parts = PurePosixPath(self.include_path).parts
                if parts and (parts[0] == '/' or parts[0] == '\\'):
                    target_parts = list(parts[1:])
                else:
                    target_parts = list(parts)
            else:
                parts = self.backup_dir_parts
                if parts:
                    if parts[0] == '/' or parts[0] == '\\':
                        target_parts = list(parts[1:])
                    elif ':' in parts[0]:
                        target_parts = [parts[0][0]] + list(parts[1:])
                    else:
                        target_parts = list(parts)
            
            if target_parts:
                rel_path = os.path.join(*target_parts)
                leaf_name = target_parts[-1]
                
                with tempfile.TemporaryDirectory(dir=self.target_dir) as tmpname:
                    shutil.move(os.path.join(self.target_dir, rel_path), tmpname)
                    
                    path_to_remove = os.path.join(self.target_dir, target_parts[0])
                    if os.path.exists(path_to_remove):
                        try:
                            shutil.rmtree(path_to_remove)
                        except OSError:
                            cmd = ['icacls', self.target_dir, '/grant', f'{os.getlogin()}:F', '/t']
                            logging.info(f"Failed to remove {common.quote_command([path_to_remove])}, retrying after running: {common.quote_command(cmd)}")
                            subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, check=False)
                            try:
                                shutil.rmtree(path_to_remove, onexc=common.remove_readonly)
                            except OSError:
                                logging.debug("failed again, giving up")

                    shutil.move(os.path.join(tmpname, leaf_name), self.target_dir)
        return summary, errmsgs

class TagSnapshotTask(WorkerTask):
    def __init__(self, env, snap_id, tag, remove, no_lock, **kwargs):
        super().__init__(**kwargs)
        self.env = env
        self.snap_id = snap_id
        self.tag = tag
        self.remove = remove
        self.no_lock = no_lock

    def run(self):
        r = Restic()
        r.tag_snapshot(self.env, self.snap_id, self.tag, remove=self.remove, no_lock=self.no_lock)

class UnlockTask(WorkerTask):
    def __init__(self, env, remove_all, **kwargs):
        super().__init__(**kwargs)
        self.env = env
        self.remove_all = remove_all

    def run(self):
        r = Restic()
        r.unlock(self.env, self.remove_all)

class GetAllPathsTask(WorkerTask):
    def __init__(self, env, no_lock, **kwargs):
        super().__init__(**kwargs)
        self.env = env
        self.no_lock = no_lock

    def run(self):
        r = Restic()
        return r.get_all_paths(self.env, self.no_lock)

class BackupTask(WorkerTask):
    def __init__(self, env, backup_dir:BackupDir, config, **kwargs):
        super().__init__(**kwargs)
        self.env = env
        self.backup_dir = backup_dir
        self.config = config

    def on_final(self):
        self.backup_dir.save_backup_result()

    def run(self):
        restic = Restic()
        entry = self.backup_dir
        cfg = self.config
        env = self.env

        try:
            entry.error = ""
            if not entry.path.exists():
                if cfg.make_vanished_permanent and entry.n_backups_since_last_perm_tag > 0:
                    try:
                        snaps = restic.list_snapshots(cfg, env, entry.get_tag(), latest_n=1)
                        if snaps:
                            latest = snaps[-1]
                            logging.info(f"Path {entry.path} vanished. Tagging snapshot {latest['short_id']} as permanent.")
                            restic.tag_snapshot(env, latest['id'], ["permanent"], no_lock=cfg.no_lock)
                            entry.n_backups_since_last_perm_tag = 0
                    except Exception as e:
                        logging.error(f"Failed to tag vanished snapshot for {entry.path}: {e}")

                if entry.enabled == 'yes':
                    raise Exception("Directory not found")
                if entry.fastscan_fingerprint == "0":
                    entry.fastscan_fingerprint = "1"
                return entry

            should_run = True
            if entry.fastscan_fingerprint == "0":
                should_run = True
            else:
                limit = cfg.prescan_file_limit
                if limit <= 0:
                    should_run = True
                else:
                    try:
                        fp = FastScan.directory_fingerprint(entry.path, limit=limit)
                        
                        if fp is None:
                            entry.fastscan_fingerprint = "0"
                            should_run = True
                            logging.info(f"Disabling pre-scan for '{entry.path}'.")
                        else:
                            if fp != entry.fastscan_fingerprint:
                                should_run = True
                                entry.fastscan_fingerprint = fp
                            else:
                                should_run = False
                    except Exception as e:
                        logging.error(f"Scan failed for {entry.path}: {e}")
                        should_run = True
            
            needs_prune = cfg.prune_enabled and (time.time() >= entry.last_prune + cfg.prune_frequency)
            full_check = needs_prune and cfg.bitrot_detection

            if full_check:
                should_run = True

            if not should_run:
                logging.info(f"Skipping {entry.path}: No changes detected during pre-scan.")
                return entry

            entry.summary = restic.run_backup_cmd(entry.path, env, full_check, cfg.no_lock, entry.iexclude)
            entry.n_backups_since_last_perm_tag += 1
            
            if needs_prune:
                if cfg.bitrot_detection:
                    logging.info(f"Checking for bitrot for {entry.path}...")
                    entry.bitrot_snap = restic.check_bitrot(cfg, env, entry.get_tag(), entry.bitrot_snap)
                
                logging.info(f"Pruning repository for {entry.path}...")
                restic.forget_some(entry.get_tag(), env)
                entry.last_prune = time.time()
                
        except Exception as ex:
            logging.error(f"Backup failed for {entry.path}: {ex}")
            entry.error = str(ex)

        return entry

class AutoDiscoveryTask(WorkerTask):
    def run(self):
        scanner = DefaultDirsScanner()
        return scanner.scan()

    def on_success(self, found):
        with common.db_conn as conn:
            if found:
                existing_rows = conn.execute("SELECT path FROM backup_dirs").fetchall()
                existing_paths = {r[0].lower() for r in existing_rows}
                
                added_count = 0
                for item in found:
                    p = item['path']
                    if p.lower() not in existing_paths:
                        exclusions = "\n".join(item['exclusions'])
                        bd = BackupDir(None, p, enabled='auto', iexclude=exclusions)
                        bd.save_ui()
                        added_count += 1
                        logging.info(f"Auto-discovery added: {p}")
                
                if added_count > 0:
                    toast = Toast()
                    toast.text_fields = ["New Backup Paths Detected", f"Added {added_count} new paths."]
                    common.wintoaster.show_toast(toast)

            conn.execute("INSERT OR REPLACE INTO status (key, value) VALUES (?, ?)", ("last_auto_discovery", str(time.time())))

class UpdateCheckTask(WorkerTask):
    def run(self):
        return UpdateChecker.fetch_latest_release_info(timeout=60)

    def on_success(self, result):
        data, remote_ver, html_url, tag = result
        uc = UpdateChecker()
        uc.last_check = time.time()
        
        is_newer = UpdateChecker.is_newer(remote_ver, common.APP_VERSION)
        uc.cached_version = json.dumps(data) if is_newer else ""
        uc.save_state()

    def on_failure(self, e):
        logging.error(f"Update check failed: {e}")
        uc = UpdateChecker()
        uc.last_check = time.time()
        uc.cached_version = "ERROR"
        uc.save_state()

class RepoFullCheckTask(WorkerTask):
    def __init__(self, env, config, segment, **kwargs):
        super().__init__(**kwargs)
        self.env = env
        self.config = config
        self.segment = segment

    def on_success(self, res):
        with common.db_conn as conn:
            if self.segment == common.FULL_CHECK_SEGMENTS:
                conn.execute("INSERT OR REPLACE INTO status (key, value) VALUES (?, ?)", ("last_full_check_segment", "-1"))
                conn.execute("INSERT OR REPLACE INTO status (key, value) VALUES (?, ?)", ("last_full_check", str(time.time())))
            else:
                conn.execute("INSERT OR REPLACE INTO status (key, value) VALUES (?, ?)", ("last_full_check_segment", str(self.segment)))
                
    def run(self):
        if self.segment == 0:
            if common.RESTIC_CACHE_DIR.exists():
                shutil.rmtree(common.RESTIC_CACHE_DIR)
                logging.info("Restic cache cleared")
            return 0
        
        restic = Restic()
        restic.run_check_cmd(self.env, self.config.no_lock, self.segment)
        return self.segment

class WorkerThread(threading.Thread):
    _task_queue:queue.Queue[WorkerTask] = queue.Queue()
    _task_id_set:set[str] = set()
    _singleton:threading.Thread = None
    _lock = threading.RLock()
    _shutdown_requested = False

    @staticmethod
    def have_task_id(task:WorkerTask) -> bool:
        with WorkerThread._lock:
            if not task or not task._task_id:
                raise ValueError()
            return task._task_id in WorkerThread._task_id_set

    @staticmethod
    def submit_task(task:WorkerTask) -> bool:
        with WorkerThread._lock:
            if WorkerThread._shutdown_requested:
                logging.info("shutdown requested, not submitting task")
                return False
            if task._task_id is None or not WorkerThread.have_task_id(task):
                if task._task_id is not None:
                    WorkerThread._task_id_set.add(task._task_id)
                WorkerThread._task_queue.put(task)
                WorkerThread.start_worker_thread()
                return True
            return False

    def __init__(self, name):
        super().__init__(daemon=True, name=name)

    def _dispatch_ui(self, func, *args):
        if not func:
            return
        if common.root:
            common.root.after(0, lambda: func(*args))
        else:
            logging.error(f"no root_tk, in shutdown? self={self}")

    def run(self):
        logging.debug("Worker thread started loop")
        with SleepInhibitor():
            while True:
                try:
                    task = self._task_queue.get(timeout=5)
                except queue.Empty:
                    with WorkerThread._lock:
                        if self._task_queue.empty():
                            WorkerThread._singleton = None
                            break
                        continue
                except:
                    break
                
                if task is None:
                    with WorkerThread._lock:
                        WorkerThread._singleton = None
                    self._task_queue.task_done()
                    break

                try:
                    try:
                        res = task.run()
                        self._dispatch_ui(task.on_success, res)
                    except Exception as e:
                        self._dispatch_ui(task.on_failure, e)
                    finally:
                        self._dispatch_ui(task.on_final)
                finally:
                    if task._task_id is not None:
                        with WorkerThread._lock:
                            self._task_id_set.remove(task._task_id)
                    self._task_queue.task_done()
        logging.debug("Worker thread exiting")

    @staticmethod
    def start_worker_thread():
        with WorkerThread._lock:
            if WorkerThread._shutdown_requested:
                logging.info("shutdown requested, not starting worker thread")
                return
            if WorkerThread._singleton and WorkerThread._singleton.is_alive():
                return
            WorkerThread._singleton = WorkerThread("WorkerThread")
            WorkerThread._singleton.start()
            logging.debug("Worker thread started.")

    @staticmethod
    def shutdown():
        with WorkerThread._lock:
            WorkerThread._shutdown_requested = True
            if WorkerThread._singleton and WorkerThread._singleton.is_alive():
                while not WorkerThread._task_queue.empty():
                    try:
                        WorkerThread._task_queue.get_nowait()
                        WorkerThread._task_queue.task_done()
                    except queue.Empty:
                        break
                WorkerThread._task_queue.put(None)

    @staticmethod
    def waitjoin():
        if WorkerThread._singleton and WorkerThread._singleton.is_alive():
            logging.debug("waiting for worker thread to finish...")
            WorkerThread._singleton.join()
            logging.debug("worker thread finished")

    @staticmethod
    def isalive() -> bool:
        with WorkerThread._lock:
            return WorkerThread._singleton and WorkerThread._singleton.is_alive()