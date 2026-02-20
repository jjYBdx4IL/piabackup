# encoding: utf-8
import datetime
import os
import time
import tkinter as tk
from pathlib import PurePosixPath
from tkinter import filedialog, messagebox, ttk

import piabackup.common as common
from piabackup.worker_thread import (FindTask, ListSnapshotsTask, LsTask,
                                     RestoreTask, TagSnapshotTask, WorkerThread)


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
        
        self.tree_snaps = ttk.Treeview(frame_left, columns=("time", "tags"), show="headings")
        self.tree_snaps.heading("time", text="Time")
        self.tree_snaps.heading("tags", text="Tags")
        self.tree_snaps.column("time", width=140)
        self.tree_snaps.column("tags", width=100)
        
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
        self.tree_snaps.bind("<Button-3>", self.show_snap_context_menu)
        
        self.node_map = {} # iid -> FileNode
        self.current_snap_id = None
        
        self.load_snapshots()

    def load_snapshots(self):
        self.lbl_status.config(text="Loading snapshots...")
        
        class SnapListTask(ListSnapshotsTask):
            def on_success(self_task, snaps):
                self.lbl_status.config(text="Select a snapshot to browse files.")
                snaps.sort(key=lambda x: x.get('_time', 0), reverse=True)
                path_tag = self.backup_dir.get_tag()
                for s in snaps:
                    ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(s['_time']))
                    tags = s.get('tags', [])
                    display_tags = [t for t in tags if t != path_tag]
                    self.tree_snaps.insert("", tk.END, values=(ts, ", ".join(display_tags)), tags=(s['short_id'], s['id']))
            def on_failure(self_task, e):
                self.lbl_status.config(text="Error loading snapshots.")
                messagebox.showerror("Error", f"Failed to list snapshots: {e}")

        WorkerThread.submit_task(SnapListTask(self.env, self.backup_dir.get_tag(), self.no_lock))

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
        
        class FileListTask(LsTask):
            def on_success(self_task, data):
                root = self.build_tree(data)
                self.lbl_status.config(text=f"Snapshot: {short_id}")
                self.populate_node("", root)
            def on_failure(self_task, e):
                self.lbl_status.config(text=f"Error loading files: {e}")
                messagebox.showerror("Error", f"Failed to list files: {e}")

        WorkerThread.submit_task(FileListTask(self.env, snap_id, self.no_lock))

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

    def show_snap_context_menu(self, event):
        item = self.tree_snaps.identify_row(event.y)
        if not item:
            return
        
        self.tree_snaps.selection_set(item)
        
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Restore...", command=self.restore_snapshot_action)
        menu.add_command(label="Restore without parent paths...", command=lambda: self.restore_snapshot_action(flatten=True))
        
        values = self.tree_snaps.item(item, "values")
        current_tags = values[1].split(", ") if values[1] else []
        is_permanent = "permanent" in current_tags
        
        menu.add_separator()
        menu.add_command(label="Remove 'permanent' tag" if is_permanent else "Add 'permanent' tag", command=lambda: self.toggle_permanent(item, is_permanent))
        
        menu.post(event.x_root, event.y_root)

    def toggle_permanent(self, item, is_removing):
        snap_id = self.tree_snaps.item(item, "tags")[1] # long id
        
        class MyTagTask(TagSnapshotTask):
            def on_success(self_task, res):
                # Update UI
                values = self.tree_snaps.item(item, "values")
                tags_str = values[1]
                tags = [t for t in tags_str.split(", ") if t]
                if is_removing:
                    if "permanent" in tags: tags.remove("permanent")
                else:
                    if "permanent" not in tags: tags.append("permanent")
                
                self.tree_snaps.item(item, values=(values[0], ", ".join(tags)))
                self.lbl_status.config(text=f"'permanent' tag {'removed' if is_removing else 'added'}.")
            def on_failure(self_task, e):
                messagebox.showerror("Error", f"Failed to update tag: {e}")

        WorkerThread.submit_task(MyTagTask(self.env, snap_id, "permanent", remove=is_removing, no_lock=self.no_lock))

    def restore_snapshot_action(self, flatten=False):
        selected = self.tree_snaps.selection()
        if not selected: return
        
        item = self.tree_snaps.item(selected[0])
        snap_id = item['tags'][1] # long id
        
        self.perform_restore(snap_id, None, flatten)

    def restore_selected(self, flatten=False):
        selected = self.tree_files.selection()
        if not selected: return
        
        node = self.node_map.get(selected[0])
        if not node: return
        
        self.perform_restore(self.current_snap_id, node.full_path, flatten)

    def perform_restore(self, snap_id, include_path=None, flatten=False):
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
            
        self.lbl_status.config(text="Restoring..." if include_path else "Restoring snapshot...")
        
        class MyRestoreTask(RestoreTask):
            def on_success(self_task, res):
                summary, errmsgs = res
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
            def on_failure(self_task, e):
                self.lbl_status.config(text="Restore failed.")
                messagebox.showerror("Error", f"Restore failed: {e}")

        WorkerThread.submit_task(MyRestoreTask(self.env, snap_id, target_dir, include_path, self.no_lock, flatten, self.backup_dir.path.parts))

    def history_selected(self):
        selected = self.tree_files.selection()
        if not selected: return
        
        node = self.node_map.get(selected[0])
        if not node or not node.full_path: return
        
        self.lbl_status.config(text="Searching history...")
        
        # Escape glob characters for restic find
        search_path = node.full_path.replace('\\', '\\\\') \
                                    .replace('[', '\\[') \
                                    .replace('?', '\\?') \
                                    .replace('*', '\\*')
        
        class HistoryFindTask(FindTask):
            def on_success(self_task, data):
                snap_ids = {res['snapshot'] for res in data}
                self.lbl_status.config(text=f"Found {len(snap_ids)} snapshots.")
                HistoryDialog(self, snap_ids, self.switch_to_snapshot)
            def on_failure(self_task, e):
                self.lbl_status.config(text="History search failed.")
                messagebox.showerror("Error", f"History search failed: {e}")

        WorkerThread.submit_task(HistoryFindTask(self.env, search_path, self.no_lock))

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
