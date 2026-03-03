# encoding: utf-8
import json
import logging
import tkinter as tk
from tkinter import ttk, messagebox

import piabackup.common as common
from piabackup.worker_thread import WorkerThread, WorkerTask
from piabackup.restic import Restic
from ui.tools import Tools

class BitrotWindow(tk.Toplevel):
    def __init__(self, parent, backup_dir, env, no_lock):
        super().__init__(parent)
        self.backup_dir = backup_dir
        self.env = env
        self.no_lock = no_lock
        self.title(f"Bit Rot Analysis - {backup_dir.path}")
        
        self.frame = ttk.Frame(self, padding=10)
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        info_frame = ttk.Frame(self.frame)
        info_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))
        
        self.lbl_status = ttk.Label(info_frame, text="Initializing...")
        self.lbl_status.pack(anchor=tk.W)
        
        self.lbl_prev = ttk.Label(info_frame, text="")
        self.lbl_prev.pack(anchor=tk.W)
        
        self.lbl_curr = ttk.Label(info_frame, text="")
        self.lbl_curr.pack(anchor=tk.W)
        
        # Text Output
        self.txt_output = tk.Text(self.frame, wrap=tk.NONE, font=("Consolas", 9))
        sb_v = ttk.Scrollbar(self.frame, orient="vertical", command=self.txt_output.yview)
        sb_h = ttk.Scrollbar(self.frame, orient="horizontal", command=self.txt_output.xview)
        self.txt_output.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)
        
        btn_frame = ttk.Frame(self.frame)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        self.btn_ack = ttk.Button(btn_frame, text="Acknowledge Bit Rot (Advance Snapshot)", command=self.acknowledge, state="disabled")
        self.btn_ack.pack(side=tk.RIGHT)
        
        sb_h.pack(side=tk.BOTTOM, fill=tk.X)
        self.txt_output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_v.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.current_bitrot_snap_id = None
        Tools.center_window(self, 800, 500)
        
        self.start_scan()

    def start_scan(self):
        self.lbl_status.config(text="Analyzing bit rot...")
        task = BitrotScanTask(self.env, self.backup_dir, self.no_lock, task_id=f"bitrot_scan_{self.backup_dir.id}")
        task.on_success = self.on_scan_success
        task.on_failure = self.on_scan_failure
        WorkerThread.submit_task(task)

    def on_scan_success(self, result):
        issues = result['issues']
        prev = result['prev']
        curr = result['curr']
        
        self.lbl_status.config(text=f"Found {len(issues)} issues.")
        
        if prev:
            self.lbl_prev.config(text=f"Previous: {prev['id']} ({prev['time']})")
        else:
            self.lbl_prev.config(text="Previous: None")
            
        if curr:
            self.lbl_curr.config(text=f"Current:  {curr['id']} ({curr['time']})")
            self.current_bitrot_snap_id = curr['id']
            self.btn_ack.state(['!disabled'])
        else:
            self.lbl_curr.config(text="Current:  None")
            
        display_list = []
        for item in issues:
            try:
                display_list.append(json.loads(item['raw']))
            except:
                display_list.append(item)
        
        self.txt_output.delete("1.0", tk.END)
        self.txt_output.insert("1.0", json.dumps(display_list, indent=4))

    def on_scan_failure(self, e):
        self.lbl_status.config(text=f"Scan failed: {e}")
        messagebox.showerror("Error", f"Scan failed: {e}")

    def acknowledge(self):
        if not self.current_bitrot_snap_id: return
        
        if not messagebox.askyesno("Confirm", "Are you sure you want to acknowledge these errors?\nThis will advance the bitrot check to this snapshot, effectively ignoring these changes for future checks."):
            return
            
        try:
            with common.db_conn as conn:
                conn.execute("UPDATE backup_dirs SET bitrot_snap=?, error='' WHERE id=?", 
                             (self.current_bitrot_snap_id, self.backup_dir.id))
            logging.info(f"Current bit rot snap id manually advanced to {self.current_bitrot_snap_id} for {self.backup_dir.path}.")
            self.backup_dir.bitrot_snap = self.current_bitrot_snap_id
            self.backup_dir.error = ""
            messagebox.showinfo("Success", "Bit rot acknowledged. You may need to refresh the main window.")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update database: {e}")

class BitrotScanTask(WorkerTask):
    def __init__(self, env, backup_dir, no_lock, **kwargs):
        super().__init__(**kwargs)
        self.env = env
        self.backup_dir = backup_dir
        self.no_lock = no_lock

    def run(self):
        restic = Restic()
        class MockCfg:
            def __init__(self, nl): self.no_lock = nl
        cfg = MockCfg(self.no_lock)
        
        snaps = restic.list_snapshots(cfg, self.env, self.backup_dir.get_tag())
        
        bitrot_snap = self.backup_dir.bitrot_snap
        prev_snap = None
        curr_snap = None
        
        if not bitrot_snap:
            if len(snaps) >= 2:
                prev_snap = snaps[0]
                curr_snap = snaps[1]
        else:
            for i, s in enumerate(snaps):
                if s['id'] == bitrot_snap:
                    if i + 1 < len(snaps):
                        prev_snap = snaps[i]
                        curr_snap = snaps[i+1]
                    break
        
        issues = []
        if prev_snap and curr_snap:
            stdout = restic.diff(self.env, prev_snap['id'], curr_snap['id'], self.no_lock)
            
            for line in stdout.splitlines():
                if not line.startswith("{"): continue
                try:
                    js = json.loads(line)
                    if js.get('message_type') == 'change':
                        if '?' in js.get('modifier', ''):
                            issues.append({
                                'path': js['path'],
                                'raw': line
                            })
                except:
                    pass
        return {
            'prev': prev_snap,
            'curr': curr_snap,
            'issues': issues
        }
