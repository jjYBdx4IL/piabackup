# encoding: utf-8
import tkinter as tk
from tkinter import ttk

from piabackup.common import center_window


class AutoDetectDialog(tk.Toplevel):
    def __init__(self, parent, paths):
        super().__init__(parent)
        self.title("New Paths Detected")
        self.result = None
        self.vars = []
        
        # Layout
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        lbl = ttk.Label(main_frame, text=f"Found {len(paths)} new paths. Select the ones you want to add:")
        lbl.pack(anchor=tk.W, pady=(0, 10))
        
        # Scrollable list container
        list_frame = ttk.Frame(main_frame, relief="sunken", borderwidth=1)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(list_frame)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        def on_canvas_configure(e):
            canvas.itemconfig(canvas_window, width=e.width)
            
        canvas.bind("<Configure>", on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        
        # Populate
        for p in paths:
            var = tk.BooleanVar(value=True)
            self.vars.append((p, var))
            cb = ttk.Checkbutton(scrollable_frame, text=str(p), variable=var)
            cb.pack(anchor=tk.W, fill=tk.X, padx=5, pady=2)
            
        # Buttons
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        ttk.Button(btn_frame, text="Select All", command=self.select_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Select None", command=self.select_none).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="Accept", command=self.accept).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        
        self.transient(parent)
        self.grab_set()
        
        center_window(self, 600, 500)

    def select_all(self):
        for _, var in self.vars:
            var.set(True)

    def select_none(self):
        for _, var in self.vars:
            var.set(False)

    def accept(self):
        self.result = [p for p, var in self.vars if var.get()]
        self.destroy()