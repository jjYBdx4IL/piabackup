# encoding: utf-8
import tkinter as tk
from tkinter import messagebox, ttk

import keyring
import logging

from piabackup import APPNAME
import piabackup.common as common
from ui.tools import Tools


class PasswordDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Set Password")
        
        frame = ttk.Frame(self, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Restic Repository Password:", font=("Segoe UI", 10)).pack(anchor=tk.W, pady=(0, 10))
        
        self.var_password = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=self.var_password, show="*")
        entry.pack(fill=tk.X, pady=(0, 5))
        entry.focus_set()
        
        self.var_show = tk.BooleanVar(value=False)
        def toggle_show():
            entry.config(show="" if self.var_show.get() else "*")
        ttk.Checkbutton(frame, text="Show password", variable=self.var_show, command=toggle_show).pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(frame, text="The password will be securely saved to the Windows Credential Manager.", 
                  font=("Segoe UI", 8), foreground="#666666", wraplength=360).pack(anchor=tk.W, pady=(0, 20))
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        ttk.Button(btn_frame, text="Save", command=self.save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)

        Tools.center_window(self, 400, 260)

    def save(self):
        password = self.var_password.get()
        if password:
            keyring.set_password(APPNAME, "repository", password)
            messagebox.showinfo(APPNAME, "Password saved to keyring.")
        else:
            try:
                keyring.delete_password(APPNAME, "repository")
            except Exception as e:
                logging.warning(f"Failed to delete password from keyring: {e}")
                pass
        self.destroy()
