# encoding: utf-8
import base64
import ctypes
from pathlib import Path
import sys
import keyring
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk, messagebox, filedialog
import sqlite3
import subprocess
import os
import time
import json
import piabackup.common as common
from piabackup.autostart import is_auto_start, is_running_in_sandbox, toggle_auto_start
from piabackup.backup_dir import BackupDir
from piabackup.DefaultDirsScanner import DefaultDirsScanner
from piabackup.auto_detect_dialog import AutoDetectDialog
from piabackup.frequency import format_frequency, parse_frequency
from piabackup.password_dialog import PasswordDialog
from piabackup.help_window import HelpWindow
from piabackup.browse_dialog import BrowseDialog
from piabackup.config import Config
from piabackup.worker_thread import WorkerThread
from piabackup.restic import Restic
from piabackup.update_checker import UpdateChecker

class SettingsWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Configuration")
        
        self.config = Config()
        self.dirs:list[BackupDir] = []
        self.deleted_dirs:list[BackupDir] = []
        self.tooltip_window = None
        self.last_tooltip_item = None
        self.last_tooltip_col = None
        self.var_autostart = tk.BooleanVar(value=is_auto_start())
        self.var_repo = tk.StringVar(value=self.config.repo)
        self.var_check_freq = tk.StringVar(value=format_frequency(self.config.full_check_frequency))
        self.var_prune_freq = tk.StringVar(value=format_frequency(self.config.prune_frequency))
        self.var_err_freq = tk.StringVar(value=format_frequency(self.config.error_check_frequency))
        self.var_bitrot = tk.BooleanVar(value=self.config.bitrot_detection)
        self.var_prune_enabled = tk.BooleanVar(value=self.config.prune_enabled)
        self.var_no_lock = tk.BooleanVar(value=self.config.no_lock)
        self.var_auto_discovery = tk.BooleanVar(value=self.config.auto_discovery)
        self.var_update_enabled = tk.BooleanVar(value=self.config.update_check_enabled)
        self.var_update_freq = tk.StringVar(value=format_frequency(self.config.update_check_frequency))
        self.var_update_toast_freq = tk.StringVar(value=format_frequency(self.config.update_check_toast_interval))
        
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, padding="20")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        
        canvas_frame = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        def on_canvas_configure(e):
            canvas.itemconfig(canvas_frame, width=e.width)
            if scrollable_frame.winfo_reqheight() > e.height:
                if not scrollbar.winfo_ismapped():
                    scrollbar.pack(side="right", fill="y")
            else:
                if scrollbar.winfo_ismapped():
                    scrollbar.pack_forget()
        
        canvas.bind("<Configure>", on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        
        frame = scrollable_frame
        
        # Autostart Section
        gen_header_frame = ttk.Frame(frame)
        gen_header_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(gen_header_frame, text="General", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        ttk.Button(gen_header_frame, text="Help", command=self.show_help).pack(side=tk.RIGHT)
        
        chk = ttk.Checkbutton(frame, text="Start application on Windows login", variable=self.var_autostart)
        chk.pack(anchor=tk.W)
        if is_running_in_sandbox():
            chk.state(['disabled'])
            ttk.Label(frame, text="(Managed by Windows App Sandbox)", foreground="gray").pack(anchor=tk.W, padx=20)
            lbl = ttk.Label(frame, text="Open Startup Settings", foreground="blue", cursor="hand2")
            lbl.bind("<Button-1>", lambda e: os.startfile("ms-settings:startupapps"))
            lbl.pack(anchor=tk.W, padx=20)
            ttk.Button(frame, text="Create Elevated Task (Task Scheduler) - RECOMMENDED", command=self.create_elevated_task).pack(anchor=tk.W, padx=20, pady=5)
        
        chk_disc = ttk.Checkbutton(frame, text="Enable automatic backup path discovery", variable=self.var_auto_discovery)
        chk_disc.pack(anchor=tk.W)
        
        err_frame = ttk.Frame(frame)
        err_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(err_frame, text="Error Check Frequency:").pack(side=tk.LEFT)
        ttk.Entry(err_frame, textvariable=self.var_err_freq, width=10).pack(side=tk.LEFT, padx=(5, 5))

        upd_frame = ttk.Frame(frame)
        upd_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Checkbutton(upd_frame, text="Check for updates", variable=self.var_update_enabled).pack(side=tk.LEFT)
        ttk.Label(upd_frame, text="Freq:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Entry(upd_frame, textvariable=self.var_update_freq, width=8).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(upd_frame, text="Toast Interval:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Entry(upd_frame, textvariable=self.var_update_toast_freq, width=8).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(upd_frame, text="Check Now", command=self.check_updates_now).pack(side=tk.LEFT, padx=(10, 0))

        ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=15)

        # Restic Section
        ttk.Label(frame, text="Restic Configuration", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 10))
        
        repo_frame = ttk.Frame(frame)
        repo_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(repo_frame, text="Repository:").pack(side=tk.LEFT)
        ttk.Button(repo_frame, text="Test Connection", command=self.test_connection).pack(side=tk.RIGHT)
        ttk.Entry(repo_frame, textvariable=self.var_repo).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        ttk.Label(frame, text="Leave empty to use RESTIC_REPOSITORY and RESTIC_PASSWORD environment variables.", 
                  font=("Segoe UI", 8), foreground="#666666", wraplength=760).pack(anchor=tk.W, pady=(0, 5))
        
        ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=15)

        freq_frame = ttk.Frame(frame)
        freq_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(freq_frame, text="Full Check Frequency:").pack(side=tk.LEFT)
        ttk.Entry(freq_frame, textvariable=self.var_check_freq, width=10).pack(side=tk.LEFT, padx=(5, 5))
        ttk.Button(freq_frame, text="Trigger Now", command=self.trigger_full_check).pack(side=tk.LEFT, padx=(0, 15))
        
        ttk.Checkbutton(freq_frame, text="Enable Prune", variable=self.var_prune_enabled, command=self.update_bitrot_state).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(freq_frame, text="Frequency:").pack(side=tk.LEFT)
        ttk.Entry(freq_frame, textvariable=self.var_prune_freq, width=10).pack(side=tk.LEFT, padx=(5, 5))
        ttk.Button(freq_frame, text="Trigger Now", command=self.trigger_prune).pack(side=tk.LEFT)
        
        bitrot_frame = ttk.Frame(frame)
        bitrot_frame.pack(fill=tk.X, pady=(5, 0))
        self.chk_bitrot = ttk.Checkbutton(bitrot_frame, text="Enable Bitrot Detection", variable=self.var_bitrot)
        self.chk_bitrot.pack(anchor=tk.W)
        ttk.Checkbutton(bitrot_frame, text="Use --no-lock (unsafe, YOU HAVE BEEN WARNED!!!)", variable=self.var_no_lock).pack(anchor=tk.W)

        ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=15)
        
        # Backup Directories Section
        ttk.Label(frame, text="Backup Directories", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 10))
        
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.tree = ttk.Treeview(list_frame, columns=("path", "enabled", "frequency", "last_run", "next_run", "summary", "error"), show="headings", height=10)
        self.tree.heading("path", text="Path", command=lambda: self.sort_tree("path", False))
        self.tree.heading("enabled", text="Enabled", command=lambda: self.sort_tree("enabled", False))
        self.tree.heading("frequency", text="Frequency", command=lambda: self.sort_tree("frequency", False))
        self.tree.heading("last_run", text="Last Run", command=lambda: self.sort_tree("last_run", False))
        self.tree.heading("next_run", text="Next Run", command=lambda: self.sort_tree("next_run", False))
        self.tree.heading("summary", text="Summary", command=lambda: self.sort_tree("summary", False))
        self.tree.heading("error", text="Error", command=lambda: self.sort_tree("error", False))
        self.tree.column("path", width=250)
        self.tree.column("enabled", width=60)
        self.tree.column("frequency", width=80)
        self.tree.column("last_run", width=120)
        self.tree.column("next_run", width=120)
        self.tree.column("summary", width=150)
        self.tree.column("error", width=150)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree.bind("<Double-1>", lambda e: self.edit_dir())
        self.tree.bind("<Motion>", self.on_tree_motion)
        self.tree.bind("<Leave>", lambda e: self.hide_tooltip())
        self.tree.bind("<Button-3>", self.show_context_menu)
        
        self.load_dirs()
        self.refresh_tree()
            
        btn_list_frame = ttk.Frame(frame)
        btn_list_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_list_frame, text="Add Folder", command=self.add_dir).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_list_frame, text="Auto Detect", command=self.auto_detect).pack(side=tk.LEFT, padx=5)
        self.btn_import = ttk.Button(btn_list_frame, text="Import from Repo", command=self.import_from_repo)
        self.btn_import.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_list_frame, text="Import List", command=self.import_paths).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_list_frame, text="Export List", command=self.export_paths).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_list_frame, text="Run Now", command=self.run_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_list_frame, text="Edit", command=self.edit_dir).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_list_frame, text="Remove", command=self.remove_dir).pack(side=tk.LEFT)

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="Save", command=self.save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)

        self.update_idletasks()
        req_width = scrollable_frame.winfo_reqwidth()
        req_height = scrollable_frame.winfo_reqheight()
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        target_width = min(req_width + 50, screen_width - 50)
        target_height = min(req_height + 40, screen_height - 100)
        
        common.center_window(self, target_width, target_height)
        self.update_bitrot_state()
        self.focus_force()

    def check_updates_now(self):
        UpdateChecker.check_now_interactive(self)

    def update_bitrot_state(self):
        if self.var_prune_enabled.get():
            self.chk_bitrot.state(['!disabled'])
        else:
            self.chk_bitrot.state(['disabled'])

    def show_help(self):
        HelpWindow(self)

    def create_elevated_task(self):
        exe_path = sys.executable
        task_name = f"{common.APPNAME}_autostart"
        uname = os.getlogin()
        
        # PowerShell script to create/update the task with desired settings
        # -AllowStartIfOnBatteries: Run even if on battery
        # -DontStopIfGoingOnBatteries: Don't stop if power is lost
        # -ExecutionTimeLimit 0: No timeout (infinite)
        ps_script = (
            f'$action = New-ScheduledTaskAction -Execute "{exe_path}"; '
            f'$trigger = New-ScheduledTaskTrigger -AtLogOn -User "{uname}"; '
            f'$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -Priority 7; '
            f'Register-ScheduledTask -TaskName "{task_name}" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force'
        )
        
        # Encode command for PowerShell (UTF-16LE base64)
        encoded_cmd = base64.b64encode(ps_script.encode('utf_16_le')).decode('utf-8')
        params = f"-NoProfile -WindowStyle Hidden -EncodedCommand {encoded_cmd}"
        
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", "powershell", params, None, 1
            )
            if ret <= 32:
                raise Exception(f"ShellExecute failed with code {ret}")
            
            messagebox.showinfo(common.APPNAME, f"Task creation command issued.\n\nTask Name: {task_name}\nTarget: {exe_path}")
        except Exception as e:
            common.log.error(f"Failed to create elevated task: {e}")
            messagebox.showerror("Error", f"Failed to create task: {e}")

    def trigger_full_check(self):
        try:
            with sqlite3.connect(common.DB_PATH) as conn:
                conn.execute("INSERT OR REPLACE INTO status (key, value) VALUES (?, ?)", ("last_full_check", "0"))
                conn.execute("INSERT OR REPLACE INTO status (key, value) VALUES (?, ?)", ("last_full_check_segment", "0"))
            messagebox.showinfo(common.APPNAME, "Full check triggered.\nIt will be executed after the next time the worker thread has finished doing the backups.")
        except Exception as e:
            common.log.error(f"Failed to trigger full check: {e}")
            messagebox.showerror("Error", f"Failed to trigger full check: {e}")

    def trigger_prune(self):
        try:
            with sqlite3.connect(common.DB_PATH) as conn:
                conn.execute("UPDATE backup_dirs SET last_prune = 0")
            messagebox.showinfo(common.APPNAME, "Prune triggered.\nIt will be executed after the next time the worker thread has finished doing the backups.")
        except Exception as e:
            common.log.error(f"Failed to trigger prune: {e}")
            messagebox.showerror("Error", f"Failed to trigger prune: {e}")

    def test_connection(self):
        repo = self.var_repo.get().strip()
        env = os.environ.copy()
        
        if repo:
            password = keyring.get_password(common.APPNAME, "repository")
            if not password:
                if messagebox.askyesno(common.APPNAME, "Repository password is not set. Set it now?"):
                    dlg = PasswordDialog(self)
                    self.wait_window(dlg)
                    password = keyring.get_password(common.APPNAME, "repository")
                
                if not password:
                    return
            env["RESTIC_REPOSITORY"] = repo
            env["RESTIC_PASSWORD"] = password
        elif "RESTIC_REPOSITORY" not in env:
            messagebox.showerror(common.APPNAME, "Repository not configured.")
            return

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        try:
            res = subprocess.run(["restic", "cat", "config"], env=env, capture_output=True, text=True, startupinfo=startupinfo)
            if res.returncode == 0:
                messagebox.showinfo(common.APPNAME, "Connection successful!")
                return
            if res.returncode == 11:
                messagebox.showinfo(common.APPNAME, "Connection successful (but repository is locked)!")
                return
            if res.returncode == 12:
                messagebox.showinfo(common.APPNAME, "Password incorrect!")
                return
            
            if res.returncode == 10:
                if messagebox.askyesno(common.APPNAME, "Repository not found or uninitialized.\nInitialize it now?"):
                    res = subprocess.run(["restic", "init"], env=env, capture_output=True, text=True, startupinfo=startupinfo)
                    if res.returncode == 0:
                        messagebox.showinfo(common.APPNAME, "Repository initialized!")
                    else:
                        messagebox.showerror(common.APPNAME, f"Initialization failed:\n{res.stderr}")
            else:
                messagebox.showerror(common.APPNAME, f"Connection failed:\n{res.stderr}")
        except Exception as e:
            messagebox.showerror(common.APPNAME, f"Error running restic: {e}")

    def load_dirs(self):
        try:
            self.dirs = BackupDir.load_dirs()
        except Exception as e:
            common.log.error(f"Failed to load backup dirs: {e}")

    @staticmethod
    def format_bytes(size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                break
            size /= 1024.0
        return f"{size:.1f} {unit}"

    def hide_tooltip(self):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
        self.last_tooltip_item = None
        self.last_tooltip_col = None

    def on_tree_motion(self, event):
        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        
        if item != self.last_tooltip_item or column != self.last_tooltip_col:
            self.hide_tooltip()
        
        if not item:
            return
            
        if item == self.last_tooltip_item and column == self.last_tooltip_col:
            return

        text_to_show = None
        try:
            if column == '#6': # Summary
                index = int(item)
                if 0 <= index < len(self.dirs):
                    d = self.dirs[index]
                    if d.summary:
                        try:
                            js = json.loads(d.summary)
                            text_to_show = json.dumps(js, indent=2)
                        except:
                            text_to_show = d.summary
            elif column == '#1': # Path
                text = self.tree.item(item, "values")[0]
                if self.is_text_truncated(text, column):
                    text_to_show = text
            elif column == '#7': # Error
                text = self.tree.item(item, "values")[6]
                if self.is_text_truncated(text, column):
                    text_to_show = text
            
            if text_to_show:
                self.last_tooltip_item = item
                self.last_tooltip_col = column
                self.show_tooltip(event.x_root, event.y_root, text_to_show)
        except Exception:
            pass

    def is_text_truncated(self, text, col_id):
        if not text: return False
        col_width = self.tree.column(col_id, 'width')
        font = tkfont.nametofont("TkDefaultFont")
        return font.measure(text) > (col_width - 10)

    def show_tooltip(self, x, y, text):
        self.tooltip_window = tk.Toplevel(self)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x+15}+{y+10}")
        lbl = tk.Label(self.tooltip_window, text=text, justify=tk.LEFT,
                    background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                    font=("Consolas", 8))
        lbl.pack()

    def sort_tree(self, col, reverse):
        key = None
        if col == "path":
            key = lambda d: str(d.path).lower()
        elif col == "enabled":
            key = lambda d: d.enabled
        elif col == "frequency":
            key = lambda d: d.frequency
        elif col == "last_run":
            key = lambda d: d.last_run
        elif col == "next_run":
            key = lambda d: d.next_run
        elif col == "error":
            key = lambda d: d.error.lower()
        elif col == "summary":
            def summary_key(d):
                try:
                    if d.summary:
                        js = json.loads(d.summary)
                        return js.get('total_bytes_processed', 0)
                except:
                    pass
                return -1
            key = summary_key

        if key:
            self.dirs.sort(key=key, reverse=reverse)
            self.refresh_tree()
            self.tree.heading(col, command=lambda: self.sort_tree(col, not reverse))

    def refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, d in enumerate(self.dirs):
            last_run_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(d.last_run)) if d.last_run > 0 else "Never"
            next_run_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(d.next_run)) if d.next_run > 0 else "ASAP"
            freq_str = format_frequency(d.frequency)
            summary_str = ""
            try:
                if d.summary:
                    js = json.loads(d.summary)
                    files = js.get('total_files_processed', 0)
                    bytes_proc = js.get('total_bytes_processed', 0)
                    summary_str = f"{self.format_bytes(bytes_proc)}, {files} files"
            except Exception:
                pass
            self.tree.insert("", tk.END, iid=str(i), values=(str(d.path), d.enabled, freq_str, last_run_str, next_run_str, summary_str, d.error))

    def import_from_repo(self):
        repo = self.var_repo.get().strip()
        env = os.environ.copy()
        
        if repo:
            password = keyring.get_password(common.APPNAME, "repository")
            if not password:
                if messagebox.askyesno(common.APPNAME, "Repository password is not set. Set it now?"):
                    dlg = PasswordDialog(self)
                    self.wait_window(dlg)
                    password = keyring.get_password(common.APPNAME, "repository")
                
                if not password:
                    return
            env["RESTIC_REPOSITORY"] = repo
            env["RESTIC_PASSWORD"] = password
        elif "RESTIC_REPOSITORY" not in env:
            messagebox.showerror(common.APPNAME, "Repository not configured.")
            return

        self.btn_import.state(['disabled'])
        self.progress_window = tk.Toplevel(self)
        self.progress_window.title("Importing")
        common.center_window(self.progress_window, 300, 100)
        ttk.Label(self.progress_window, text="Reading repository snapshots...\nPlease wait.", padding=20).pack()
        self.progress_window.transient(self)
        self.progress_window.grab_set()
        self.progress_window.protocol("WM_DELETE_WINDOW", lambda: None)

        def run_import(env, no_lock):
            r = Restic()
            return r.get_all_paths(env, no_lock)

        WorkerThread.submit_task(run_import, env, self.var_no_lock.get())
        self.check_import_result()

    def check_import_result(self):
        res = WorkerThread.get_result()
        if res:
            status, data = res
            self.progress_window.destroy()
            self.btn_import.state(['!disabled'])
            
            if status == "success":
                self.process_import_data(data)
            else:
                messagebox.showerror(common.APPNAME, f"Import failed: {data}")
        else:
            self.after(200, self.check_import_result)

    def process_import_data(self, paths):
        count = 0
        existing_paths = {d.path for d in self.dirs}
        
        for p in sorted(paths, key=lambda x: str(x).lower()):
            if p not in existing_paths:
                self.dirs.append(BackupDir(None, str(p)))
                existing_paths.add(p)
                count += 1
        
        if count > 0:
            self.refresh_tree()
            messagebox.showinfo(common.APPNAME, f"Imported {count} new folders from repository.")
        else:
            messagebox.showinfo(common.APPNAME, "No new folders found in repository.")

    def import_paths(self):
        filename = filedialog.askopenfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not filename:
            return
        try:
            count = 0
            existing_paths = {d.path for d in self.dirs}
            lines = []
            with open(filename, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
            
            for path_str in sorted(lines, key=str.lower):
                try:
                    p = Path(path_str)
                    if p not in existing_paths:
                        self.dirs.append(BackupDir(None, str(p)))
                        existing_paths.add(p)
                        count += 1
                except Exception:
                    pass
            if count > 0:
                self.refresh_tree()
                messagebox.showinfo(common.APPNAME, f"Imported {count} new paths.")
            else:
                messagebox.showinfo(common.APPNAME, "No new paths found in file.")
        except Exception as e:
            messagebox.showerror(common.APPNAME, f"Failed to import: {e}")

    def export_paths(self):
        filename = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not filename:
            return
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for d in sorted(self.dirs, key=lambda d: str(d.path).lower()):
                    f.write(f"{d.path}\n")
            messagebox.showinfo(common.APPNAME, f"Exported {len(self.dirs)} paths.")
        except Exception as e:
            messagebox.showerror(common.APPNAME, f"Failed to export: {e}")

    def add_dir(self):
        path = filedialog.askdirectory()
        if path:
            # Check for duplicates
            for d in self.dirs:
                if d.path == Path(path):
                    return
            self.dirs.append(BackupDir(None, path))
            self.refresh_tree()

    def auto_detect(self):
        try:
            scanner = DefaultDirsScanner()
            paths = scanner.scan()
            
            existing_paths = {str(d.path).lower() for d in self.dirs}
            new_paths = []
            
            for p in paths:
                if str(p).lower() not in existing_paths:
                    new_paths.append(p)
            
            if not new_paths:
                messagebox.showinfo(common.APPNAME, "No new paths found.")
                return

            dlg = AutoDetectDialog(self, new_paths)
            self.wait_window(dlg)
            
            if dlg.result:
                count = 0
                for p in dlg.result:
                    self.dirs.append(BackupDir(None, str(p), enabled='auto'))
                    existing_paths.add(str(p).lower())
                    count += 1
                
                if count > 0:
                    self.refresh_tree()
                    messagebox.showinfo(common.APPNAME, f"Added {count} new paths.")
        except Exception as e:
            common.log.error(f"Auto detect failed: {e}")
            messagebox.showerror(common.APPNAME, f"Auto detect failed: {e}")

    def run_selected(self):
        selected = self.tree.selection()
        if not selected: return
        
        updated_db = False
        try:
            with sqlite3.connect(common.DB_PATH) as conn:
                for item in selected:
                    path = self.tree.item(item)['values'][0]
                    entry = next((d for d in self.dirs if str(d.path) == path), None)
                    if entry:
                        if entry.id is not None:
                            entry.schedule_run_now(conn)
                            updated_db = True
        except Exception as e:
            common.log.error(f"Failed to update next_run: {e}")
            messagebox.showerror(common.APPNAME, f"Failed to schedule run: {e}")
            
        self.refresh_tree()
        if updated_db:
            WorkerThread.start_worker_thread()

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        
        self.tree.selection_set(item)
        
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Open in Explorer", command=self.open_in_explorer)
        menu.add_command(label="Browse", command=self.open_browse_dialog)
        
        menu.post(event.x_root, event.y_root)

    def open_in_explorer(self):
        selected = self.tree.selection()
        if not selected: return
        path = self.tree.item(selected[0])['values'][0]
        try:
            os.startfile(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open explorer: {e}")

    def open_browse_dialog(self):
        selected = self.tree.selection()
        if not selected: return
        path_str = self.tree.item(selected[0])['values'][0]
        entry = next((d for d in self.dirs if str(d.path) == path_str), None)
        if not entry: return

        repo = self.var_repo.get().strip()
        env = os.environ.copy()
        
        if repo:
            password = keyring.get_password(common.APPNAME, "repository")
            if not password:
                if messagebox.askyesno(common.APPNAME, "Repository password is not set. Set it now?"):
                    dlg = PasswordDialog(self)
                    self.wait_window(dlg)
                    password = keyring.get_password(common.APPNAME, "repository")
                
                if not password:
                    return
            env["RESTIC_REPOSITORY"] = repo
            env["RESTIC_PASSWORD"] = password
        elif "RESTIC_REPOSITORY" not in env:
            messagebox.showerror(common.APPNAME, "Repository not configured.")
            return
            
        BrowseDialog(self, entry, env, self.var_no_lock.get())

    def edit_dir(self):
        selected = self.tree.selection()
        if not selected:
            return
        
        # Find the config entry
        item_vals = self.tree.item(selected[0])['values']
        path = item_vals[0]
        entry = next((d for d in self.dirs if str(d.path) == path), None)
        if not entry:
            return

        # Dialog
        dlg = tk.Toplevel(self)
        dlg.title("Edit Folder")
        common.center_window(dlg, 300, 200)
        
        ttk.Label(dlg, text="Path: " + path, wraplength=280).pack(pady=10, padx=10)
        
        var_enabled = tk.StringVar(value=entry.enabled)
        ttk.Label(dlg, text="Enabled:").pack(anchor=tk.W, padx=10)
        ttk.Combobox(dlg, textvariable=var_enabled, values=["yes", "no", "auto"], state="readonly").pack(fill=tk.X, padx=10, pady=5)
        
        var_freq = tk.StringVar(value=format_frequency(entry.frequency))
        ttk.Label(dlg, text="Frequency (e.g. 1w 2d 30m):").pack(anchor=tk.W, padx=10)
        ttk.Entry(dlg, textvariable=var_freq).pack(fill=tk.X, padx=10, pady=5)
        
        def save_edit():
            try:
                new_freq = parse_frequency(var_freq.get())
            except Exception as e:
                messagebox.showerror("Error", str(e))
                return
            entry.enabled = var_enabled.get()
            entry.frequency = new_freq
            self.refresh_tree()
            dlg.destroy()
            
        ttk.Button(dlg, text="OK", command=save_edit).pack(pady=10)

    def remove_dir(self):
        selected = self.tree.selection()
        for item in selected:
            path = self.tree.item(item)['values'][0]
            entry = next((d for d in self.dirs if str(d.path) == path), None)
            if entry:
                if entry.id is not None:
                    self.deleted_dirs.append(entry)
                self.dirs.remove(entry)
        self.refresh_tree()

    def save(self):
        if self.var_autostart.get() != is_auto_start():
            toggle_auto_start(self.var_autostart.get())
        
        try:
            self.config.full_check_frequency = parse_frequency(self.var_check_freq.get())
            self.config.prune_frequency = parse_frequency(self.var_prune_freq.get())
            self.config.error_check_frequency = parse_frequency(self.var_err_freq.get())
            self.config.bitrot_detection = self.var_bitrot.get()
            self.config.prune_enabled = self.var_prune_enabled.get()
            self.config.no_lock = self.var_no_lock.get()
            self.config.auto_discovery = self.var_auto_discovery.get()
            self.config.update_check_enabled = self.var_update_enabled.get()
            self.config.update_check_frequency = max(common.MIN_UPDATE_CHECK_IVAL, parse_frequency(self.var_update_freq.get()))
            self.config.update_check_toast_interval = parse_frequency(self.var_update_toast_freq.get())
        except Exception as e:
            messagebox.showerror(common.APPNAME, f"Invalid frequency: {e}")
            return

        self.config.repo = self.var_repo.get()
        self.config.save()
        
        try:
            with sqlite3.connect(common.DB_PATH) as conn:
                # Handle deletions
                for entry in self.deleted_dirs:
                    entry.delete(conn)
                
                # Handle updates and inserts
                for d in self.dirs:
                    d.save_ui(conn)
        except Exception as e:
            common.log.error(f"Failed to save backup dirs: {e}")
            messagebox.showerror(common.APPNAME, f"Failed to save backup directories: {e}")
            
        self.destroy()
