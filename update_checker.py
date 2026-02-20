# encoding: utf-8
import json
import logging
import threading
import time
import urllib.request
import webbrowser
from tkinter import messagebox

from windows_toasts import Toast

import piabackup.common as common


class UpdateChecker:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UpdateChecker, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.last_check = 0.0
        self.last_toast = 0.0
        self.cached_version = ""
        self._init_db()

    def _init_db(self):
        with common.db_conn as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS update_checker (id INTEGER PRIMARY KEY, last_check REAL, last_toast REAL, cached_version TEXT)")
            conn.execute("INSERT OR IGNORE INTO update_checker (id, last_check, last_toast, cached_version) VALUES (1, 0, 0, '')")
            row = conn.execute("SELECT last_check, last_toast, cached_version FROM update_checker WHERE id=1").fetchone()
            self.last_check, self.last_toast, self.cached_version = row

    def save_state(self):
        with common.db_conn as conn:
            conn.execute("UPDATE update_checker SET last_check=?, last_toast=?, cached_version=? WHERE id=1", 
                         (self.last_check, self.last_toast, self.cached_version))

    @staticmethod
    def is_newer(remote_ver, local_ver):
        try:
            p1 = [int(x) for x in remote_ver.split('.')]
            p2 = [int(x) for x in local_ver.split('.')]
            return p1 > p2
        except:
            return remote_ver != local_ver

    @staticmethod
    def fetch_latest_release_info(timeout=10):
        with urllib.request.urlopen(common.APP_UPDATE_CHECK_URL, timeout=timeout) as response:
            data = json.loads(response.read().decode())
            tag = data.get("tag_name", "")
            html_url = data.get("html_url", "")
            remote_ver = tag.lstrip("v")
            if not tag or not html_url or not remote_ver:
                raise ValueError("Invalid release data")
            logging.debug(f"Fetched latest release info: tag={tag}, html_url={html_url}, remote_ver={remote_ver}")
            return data, remote_ver, html_url, tag

    def show_toast_if_needed(self, toast_interval) -> bool:
        if self.cached_version and self.cached_version != "ERROR":
            if time.time() > self.last_toast + toast_interval:
                self.last_toast = time.time()
                self.save_state()
                try:
                    data = json.loads(self.cached_version)
                    tag = data.get("tag_name", "")
                    html_url = data.get("html_url", "")
                    self._emit_toast(tag, html_url)
                    return True
                except Exception as e:
                    logging.error(f"Failed to show update toast: {e}")
        return False

    @staticmethod
    def _emit_toast(tag, html_url):
        toast = Toast()
        toast.text_fields = ["Update Available", f"New version {tag} is available."]
        toast.on_activated = lambda _: webbrowser.open(html_url)
        common.wintoaster.show_toast(toast)

    @staticmethod
    def check_now_interactive(root_tk):
        def task():
            try:
                data, remote_ver, html_url, tag = UpdateChecker.fetch_latest_release_info()
                if UpdateChecker.is_newer(remote_ver, common.APP_VERSION):
                    root_tk.after(0, lambda: UpdateChecker._emit_toast(tag, html_url))
                else:
                    root_tk.after(0, lambda: messagebox.showinfo(common.APPNAME, f"You are up to date (Version {common.APP_VERSION})."))
            except Exception as e:
                logging.error(f"Update check failed: {e}")
                err_msg = str(e)
                root_tk.after(0, lambda: messagebox.showerror("Error", f"Update check failed: {err_msg}"))

        threading.Thread(target=task, daemon=True).start()
