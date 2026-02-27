# encoding: utf-8
import os
import tkinter as tk
from tkinter import ttk

import piabackup.common as common
from ui.tools import Tools


class HelpWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Help")
        
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text = tk.Text(frame, wrap=tk.WORD, yscrollcommand=scrollbar.set, font=("Segoe UI", 10), padx=15, pady=15)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text.yview)
        
        text.tag_configure("h1", font=("Segoe UI", 12, "bold"), spacing3=10)
        text.tag_configure("h2", font=("Segoe UI", 10, "bold"), spacing3=5)
        text.tag_configure("body", font=("Segoe UI", 10), spacing1=2)
        
        self.load_help_content(text)
        
        text.config(state=tk.DISABLED)
        
        Tools.center_window(self, 700, 600)

    def load_help_content(self, widget):
        md_path = common.ASSETS_DIR / "help_window.md"

        if not os.path.exists(md_path):
            widget.insert(tk.END, "Help file not found.", "body")
            return

        try:
            with open(md_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip()
                    if not line:
                        widget.insert(tk.END, "\n")
                        continue
                    
                    tag = "body"
                    content = line
                    
                    if line.startswith("# "):
                        tag = "h1"
                        content = line[2:]
                    elif line.startswith("## "):
                        tag = "h2"
                        content = line[3:]
                    
                    widget.insert(tk.END, content + "\n", tag)
        except Exception as e:
            widget.insert(tk.END, f"Error loading help: {e}", "body")
