# encoding: utf-8
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import shutil
import tempfile
import threading
import time
import datetime
from pathlib import PurePosixPath
import piabackup.common as common
from piabackup.restic import Restic

class FileNode:
    def __init__(self, name, is_dir, size, mtime, full_path):
        self.name = name
        self.is_dir = is_dir
        self.size = size
        self.mtime = mtime
        self.full_path = full_path
        self.children = {} # name -> FileNode

class BrowseDialog(tk.Toplevel):
    def __init__(self, parent, backup_dir, env, no_lock):
        super().__init__(parent)
        self.backup_dir = backup_dir
        self.env = env
        self.no_lock = no_lock
        self.title(f"Browse: {backup_dir.path}")
        
        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)
        
        # Left: Snapshots
        frame_left = ttk.Frame(self.paned)
        self.paned.add(frame_left, weight=1)
        
        ttk.Label(frame_left, text="Snapshots").pack(anchor=tk.W, padx=5, pady=5)
        
        self.tree_snaps = ttk.Treeview(frame_left, columns=("time",), show="headings")
        self.tree_snaps.heading("time", text="Time")
        self.tree_snaps.column("time", width=160)
        
        sb_snaps = ttk.Scrollbar(frame_left, orient="vertical", command=self.tree_snaps.yview)
        self.tree_snaps.configure(yscroll=sb_snaps.set)
        
        self.tree_snaps.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_snaps.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Right: Files
        frame_right = ttk.Frame(self.paned)
        self.paned.add(frame_right, weight=4)
        
        self.lbl_status = ttk.Label(frame_right, text="Select a snapshot to browse files.")
        self.lbl_status.pack(anchor=tk.W, padx=5, pady=5)
        
        self.tree_files = ttk.Treeview(frame_right, columns=("size", "mtime"), show="tree headings")
        self.tree_files.heading("#0", text="Name")
        self.tree_files.heading("size", text="Size")
        self.tree_files.heading("mtime", text="Modified")
        
        self.tree_files.column("#0", width=400)
        self.tree_files.column("size", width=100, anchor=tk.E)
        self.tree_files.column("mtime", width=150)
        
        sb_files = ttk.Scrollbar(frame_right, orient="vertical", command=self.tree_files.yview)
        self.tree_files.configure(yscroll=sb_files.set)
        
        self.tree_files.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_files.pack(side=tk.RIGHT, fill=tk.Y)
        
        common.center_window(self, 1000, 600)
        
        self.tree_snaps.bind("<<TreeviewSelect>>", self.on_snap_select)
        self.tree_files.bind("<<TreeviewOpen>>", self.on_folder_open)
        self.tree_files.bind("<Button-3>", self.show_context_menu)
        
        self.node_map = {} # iid -> FileNode
        self.current_snap_id = None
        
        self.load_snapshots()

    def load_snapshots(self):
        self.lbl_status.config(text="Loading snapshots...")
        
        def task():
            try:
                r = Restic()
                
                # Mock config to pass no_lock setting
                class MockConfig:
                    def __init__(self, no_lock):
                        self.no_lock = no_lock
                
                cfg = MockConfig(self.no_lock)
                snaps = r.list_snapshots(cfg, self.env, self.backup_dir.get_tag())
                
                def update_ui():
                    try:
                        self.lbl_status.config(text="Select a snapshot to browse files.")
                        # Sort by time descending
                        snaps.sort(key=lambda x: x.get('_time', 0), reverse=True)
                        for s in snaps:
                            ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(s['_time']))
                            self.tree_snaps.insert("", tk.END, values=(ts,), tags=(s['short_id'], s['id']))
                    except tk.TclError:
                        pass # Window destroyed
                
                try:
                    self.after(0, update_ui)
                except: pass
            except Exception as e:
                err_msg = str(e)
                def show_err():
                    try:
                        self.lbl_status.config(text="Error loading snapshots.")
                        messagebox.showerror("Error", f"Failed to list snapshots: {err_msg}")
                    except: pass
                try:
                    self.after(0, show_err)
                except: pass

        threading.Thread(target=task, daemon=True).start()

    def on_snap_select(self, event):
        selected = self.tree_snaps.selection()
        if not selected: return
        
        item = self.tree_snaps.item(selected[0])
        snap_id = item['tags'][1] # long id
        short_id = item['tags'][0]
        
        if snap_id == self.current_snap_id:
            return
            
        self.current_snap_id = snap_id
        self.load_files(snap_id, short_id)

    def load_files(self, snap_id, short_id):
        self.tree_files.delete(*self.tree_files.get_children())
        self.node_map.clear()
        self.lbl_status.config(text=f"Loading files for snapshot {short_id}...")
        
        def task():
            try:
                r = Restic()
                items = r.ls(self.env, snap_id, self.no_lock)
                root = self.build_tree(items)
                
                def update_ui():
                    try:
                        self.lbl_status.config(text=f"Snapshot: {short_id}")
                        self.populate_node("", root)
                    except tk.TclError:
                        pass
                
                self.after(0, update_ui)
            except Exception as e:
                err_msg = str(e)
                def show_err():
                    self.lbl_status.config(text=f"Error loading files: {err_msg}")
                    messagebox.showerror("Error", f"Failed to list files: {err_msg}")
                self.after(0, show_err)

        threading.Thread(target=task, daemon=True).start()

    def build_tree(self, items):
        root = FileNode("/", True, 0, "", "/")
        
        for item in items:
            path_str = item.get("path")
            if not path_str: continue
            
            # restic paths start with /, e.g. /C/Users/...
            parts = PurePosixPath(path_str).parts
            
            current = root
            for i, part in enumerate(parts):
                if part == "/" or part == "\\": continue
                
                if part not in current.children:
                    # Default intermediate node
                    node = FileNode(part, True, 0, "", "")
                    current.children[part] = node
                
                current = current.children[part]
                
                # Update node info if this is the actual item
                if i == len(parts) - 1:
                    current.is_dir = (item["type"] == "dir")
                    current.size = item.get("size", 0)
                    if item.get("mtime"):
                        try:
                            dt = datetime.datetime.fromisoformat(item["mtime"].replace("Z", "+00:00"))
                            current.mtime = dt.strftime('%Y-%m-%d %H:%M')
                        except: pass
                    current.full_path = path_str

        # Navigate to backup_dir root
        current = root
        parts = self.backup_dir.path.parts
        target_parts = []
        
        if parts:
            if parts[0] == '/' or parts[0] == '\\':
                target_parts = list(parts[1:])
            elif ':' in parts[0]:
                # Windows drive "C:\\" -> "C"
                target_parts = [parts[0][0]] + list(parts[1:])
            else:
                target_parts = list(parts)
        
        for part in target_parts:
            if part in current.children:
                current = current.children[part]
            else:
                break

        return current

    def populate_node(self, parent_iid, node):
        # Sort children: directories first, then files. Alphabetical.
        children = list(node.children.values())
        children.sort(key=lambda x: (not x.is_dir, x.name.lower()))
        
        for child in children:
            icon = "📁 " if child.is_dir else "📄 "
            size_str = self.format_size(child.size) if not child.is_dir else ""
            
            iid = self.tree_files.insert(parent_iid, tk.END, text=icon + child.name, values=(size_str, child.mtime), open=False)
            self.node_map[iid] = child
            
            if child.is_dir:
                # Add dummy child to make it expandable
                self.tree_files.insert(iid, tk.END, text="dummy")

    def on_folder_open(self, event):
        iid = self.tree_files.focus()
        if not iid: return
        
        node = self.node_map.get(iid)
        if not node or not node.is_dir: return
        
        # Check if already loaded (dummy child exists?)
        children = self.tree_files.get_children(iid)
        if len(children) == 1 and self.tree_files.item(children[0], "text") == "dummy":
            self.tree_files.delete(children[0])
            self.populate_node(iid, node)

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                break
            size /= 1024.0
        return f"{size:.1f} {unit}"

    def show_context_menu(self, event):
        item = self.tree_files.identify_row(event.y)
        if not item:
            return
        
        self.tree_files.selection_set(item)
        
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Restore...", command=self.restore_selected)
        menu.add_command(label="Restore without parent paths...", command=lambda: self.restore_selected(flatten=True))
        menu.add_command(label="History...", command=self.history_selected)
        
        menu.post(event.x_root, event.y_root)

    def restore_selected(self, flatten=False):
        selected = self.tree_files.selection()
        if not selected: return
        
        node = self.node_map.get(selected[0])
        if not node: return
        
        target_dir = filedialog.askdirectory(title="Select Empty Restore Destination")
        if not target_dir: return
        
        if not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir)
            except Exception as e:
                messagebox.showerror("Error", f"Could not create destination directory: {e}")
                return

        if os.listdir(target_dir):
            messagebox.showerror("Error", "The destination directory must be empty.")
            return
            
        self.lbl_status.config(text="Restoring...")
        
        def task():
            try:
                r = Restic()
                summary, errmsgs = r.restore(self.env, self.current_snap_id, target_dir, node.full_path, self.no_lock)

                if flatten:                
                    parts = PurePosixPath(node.full_path).parts
                    if parts and (parts[0] == '/' or parts[0] == '\\'):
                        parts = parts[1:]
                    rel_path = os.path.join(*parts)
                    with tempfile.TemporaryDirectory(dir=target_dir) as tmpname:
                        shutil.move(os.path.join(target_dir, rel_path), tmpname)
                        shutil.rmtree(os.path.join(target_dir, rel_path[0]), ignore_errors=True)
                        shutil.move(os.path.join(tmpname, node.name), target_dir)
                    
                def success():
                    self.lbl_status.config(text="Restore successful.")
                    msg = "Restore completed successfully."
                    if errmsgs:
                        msg += "\n\nIgnored errors:\n" + "\n".join(errmsgs)
                    if summary:
                        msg += "\n\n" + summary.strip()
                    if messagebox.askyesno("Restore", msg + "\n\nDo you want to open the target folder?"):
                        try:
                            os.startfile(target_dir)
                        except Exception as e:
                            messagebox.showerror("Error", f"Failed to open folder: {e}")
                self.after(0, success)
            except Exception as e:
                err_msg = str(e)
                def fail():
                    self.lbl_status.config(text="Restore failed.")
                    messagebox.showerror("Error", f"Restore failed: {err_msg}")
                self.after(0, fail)
                
        threading.Thread(target=task, daemon=True).start()

    def history_selected(self):
        selected = self.tree_files.selection()
        if not selected: return
        
        node = self.node_map.get(selected[0])
        if not node or not node.full_path: return
        
        self.lbl_status.config(text="Searching history...")
        
        def task():
            try:
                r = Restic()
                # Escape glob characters for restic find
                search_path = node.full_path.replace('\\', '\\\\') \
                                            .replace('[', '\\[') \
                                            .replace('?', '\\?') \
                                            .replace('*', '\\*')
                results = r.find(self.env, search_path, self.no_lock)
                snap_ids = {res['snapshot'] for res in results}
                
                def show():
                    self.lbl_status.config(text=f"Found {len(snap_ids)} snapshots.")
                    HistoryDialog(self, snap_ids, self.switch_to_snapshot)
                self.after(0, show)
            except Exception as e:
                err_msg = str(e)
                def fail():
                    self.lbl_status.config(text="History search failed.")
                    messagebox.showerror("Error", f"History search failed: {err_msg}")
                self.after(0, fail)

        threading.Thread(target=task, daemon=True).start()

    def switch_to_snapshot(self, snap_id):
        for item in self.tree_snaps.get_children():
            tags = self.tree_snaps.item(item, "tags")
            if tags[1].startswith(snap_id) or snap_id.startswith(tags[1]):
                self.tree_snaps.selection_set(item)
                self.tree_snaps.see(item)
                self.on_snap_select(None)
                return

class HistoryDialog(tk.Toplevel):
    def __init__(self, parent, snap_ids, on_select):
        super().__init__(parent)
        self.title("File History")
        
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True)
        
        tree = ttk.Treeview(frame, columns=("time", "id"), show="headings")
        tree.heading("time", text="Time")
        tree.heading("id", text="Snapshot ID")
        tree.column("time", width=150)
        tree.column("id", width=100)
        
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscroll=sb.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        
        count = 0
        for item in parent.tree_snaps.get_children():
            vals = parent.tree_snaps.item(item, "values")
            tags = parent.tree_snaps.item(item, "tags")
            sid = tags[1]
            if sid in snap_ids:
                tree.insert("", tk.END, values=(vals[0], tags[0]), tags=(sid,))
                count += 1
        
        tree.bind("<Double-1>", lambda e: self.on_double_click(tree, on_select))
        
        common.center_window(self, 400, 300)
        if count == 0:
            ttk.Label(self, text="No snapshots found (sync issue?)").pack()
        
        self.lift()
        self.focus_force()

    def on_double_click(self, tree, on_select):
        selected = tree.selection()
        if not selected: return
        sid = tree.item(selected[0], "tags")[0]
        on_select(sid)
        self.destroy()
