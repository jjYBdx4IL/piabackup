# encoding: utf-8
import json
import threading
import time
import urllib.request
import webbrowser
import sqlite3
from tkinter import messagebox
from windows_toasts import Toast
import piabackup.common as common
from piabackup.config import Config

class UpdateChecker:
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
            common.log.debug(f"Fetched latest release info: tag={tag}, html_url={html_url}, remote_ver={remote_ver}")
            return data, remote_ver, html_url, tag

    @staticmethod
    def show_toast(tag, html_url):
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
                    root_tk.after(0, lambda: UpdateChecker.show_toast(tag, html_url))
                else:
                    root_tk.after(0, lambda: messagebox.showinfo(common.APPNAME, f"You are up to date (Version {common.APP_VERSION})."))
            except Exception as e:
                common.log.error(f"Update check failed: {e}")
                root_tk.after(0, lambda: messagebox.showerror("Error", f"Update check failed: {e}"))

        threading.Thread(target=task, daemon=True).start()

    @staticmethod
    def background_check_loop(root_tk):
        if root_tk:
            root_tk.after(3600000, lambda: UpdateChecker.background_check_loop(root_tk)) # Check every hour
        
        def bg_check():
            try:
                cfg = Config()
                if not cfg.update_check_enabled:
                    return

                with sqlite3.connect(common.DB_PATH) as conn:
                    last_check = float(conn.execute("SELECT value FROM status WHERE key = 'last_update_check'").fetchone()[0])
                    last_toast = float(conn.execute("SELECT value FROM status WHERE key = 'last_update_toast'").fetchone()[0])
                    cached_ver_json = conn.execute("SELECT value FROM status WHERE key = 'cached_latest_version'").fetchone()[0]
                    
                    # Check for updates if due
                    if time.time() > last_check + (cfg.update_check_frequency if cached_ver_json != "ERROR" else common.MIN_UPDATE_CHECK_IVAL):
                        try:
                            conn.execute("UPDATE status SET value = ? WHERE key = 'last_update_check'", (str(time.time()),))
                            data, remote_ver, html_url, tag = UpdateChecker.fetch_latest_release_info(timeout=60)
                            
                            is_newer = UpdateChecker.is_newer(remote_ver, common.APP_VERSION)
                            
                            cached_ver_json = json.dumps(data) if is_newer else ""
                            conn.execute("UPDATE status SET value = ? WHERE key = 'cached_latest_version'", (cached_ver_json,))
                        except Exception as e:
                            common.log.error(f"Background update check failed: {e}")
                            cached_ver_json = "ERROR"
                            conn.execute("UPDATE status SET value = ? WHERE key = 'cached_latest_version'", ("ERROR",))

                    # Show toast if we have a pending update and toast interval passed
                    if cached_ver_json and cached_ver_json != "ERROR" and time.time() > last_toast + cfg.update_check_toast_interval:
                        conn.execute("UPDATE status SET value = ? WHERE key = 'last_update_toast'", (str(time.time()),))
                        data = json.loads(cached_ver_json)
                        tag = data.get("tag_name", "")
                        html_url = data.get("html_url", "")
                        root_tk.after(0, lambda: UpdateChecker.show_toast(tag, html_url))
                        
            except Exception as e:
                common.log.error(f"Update check loop error: {e}")

        threading.Thread(target=bg_check, daemon=True, name="UpdateCheckThread").start()
