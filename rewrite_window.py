# encoding: utf-8
import os
import tkinter as tk
from tkinter import ttk
import piabackup.common as common
from piabackup.worker_thread import StreamingResticTask, WorkerThread


class RewriteWindow(tk.Toplevel):
    def __init__(self, parent, backup_dir, env, no_lock):
        super().__init__(parent)
        self.backup_dir = backup_dir
        self.env = env
        self.no_lock = no_lock
        self.title(f"Rewrite - {os.path.basename(self.backup_dir.path)}")
        common.center_window(self, 600, 400)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Controls
        controls_frame = ttk.Frame(self, padding="10")
        controls_frame.grid(row=0, column=0, sticky="ew")
        
        self.start_button = ttk.Button(controls_frame, text="Start", command=self.start_rewrite)
        self.start_button.pack(side=tk.LEFT)

        self.var_dry_run = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls_frame, text="Dry Run", variable=self.var_dry_run).pack(side=tk.LEFT, padx=5)

        # Output
        output_frame = ttk.Frame(self, padding="0 10 10 10")
        output_frame.grid(row=1, column=0, sticky="nsew")
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)

        self.output_text = tk.Text(output_frame, wrap=tk.WORD, state=tk.DISABLED, bg="#f0f0f0")
        self.output_text.grid(row=0, column=0, sticky="nsew")

        scroll_bar = ttk.Scrollbar(output_frame, command=self.output_text.yview)
        scroll_bar.grid(row=0, column=1, sticky="ns")
        self.output_text['yscrollcommand'] = scroll_bar.set

        self.transient(parent)

        common.center_window(self, 600, 400)

    def append_output(self, text):
        self.output_text.config(state=tk.NORMAL)
        self.output_text.insert(tk.END, text)
        self.output_text.see(tk.END)
        self.output_text.config(state=tk.DISABLED)
        self.update_idletasks()

    def start_rewrite(self):
        self.start_button.config(state=tk.DISABLED)
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete(1.0, tk.END)
        self.output_text.config(state=tk.DISABLED)

        class RewriteTask(StreamingResticTask):
            def __init__(self_task, env, no_lock, path, tag, iexclude, dry_run):
                args = ["rewrite", "--path", str(path), "--tag", tag, "--forget"]
                if dry_run:
                    args.append("--dry-run")
                super().__init__(env, no_lock, *args, iexclude=iexclude, backup_path=path)

            def on_output(self_task, line):
                self.append_output(line)

            def on_success(self_task, result):
                self.append_output("\nRewrite completed successfully.")
                self.start_button.config(state=tk.NORMAL)

            def on_failure(self_task, e):
                self.append_output(f"\nRewrite failed: {e}")
                self.start_button.config(state=tk.NORMAL)

        task = RewriteTask(self.env, self.no_lock, self.backup_dir.path, self.backup_dir.get_tag(), self.backup_dir.iexclude, self.var_dry_run.get())
        WorkerThread.submit_task(task)
