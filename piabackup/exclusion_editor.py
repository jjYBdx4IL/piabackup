# encoding: utf-8
import fnmatch
import os
import re
import tkinter as tk
from tkinter import ttk


def translate_pattern_to_regex(pattern):
    """
    Translates a restic/gitignore-style pattern to a regular expression.
    This version is simplified and more robust.
    """
    if pattern.startswith('#') or not pattern.strip():
        return None

    dir_only = pattern.endswith('/')
    if dir_only:
        pattern = pattern[:-1]

    if pattern.startswith('/'):
        anchored = True
        pattern = pattern[1:]
    else:
        anchored = False

    # Translate glob special characters to regex
    regex_body = ''
    for char in pattern:
        if char == '*':
            regex_body += '[^/]*'
        elif char == '?':
            regex_body += '[^/]'
        else:
            regex_body += re.escape(char)

    if anchored:
        # Anchored to the start of the relative path
        final_regex = f'^{regex_body}'
    else:
        # Unanchored patterns can match after any directory prefix (or none)
        final_regex = f'(^|.*/){regex_body}'

    # Handle file vs directory matching at the end
    if dir_only:
        # Must match a directory
        final_regex += '/$'
    else:
        # Can match a file (no slash) or a directory (trailing slash)
        final_regex += '(/)?$'

    return re.compile(final_regex)


class ExclusionEditor(tk.Toplevel):
    def __init__(self, parent, backup_dir, on_save):
        super().__init__(parent)
        self.backup_dir = backup_dir
        self.on_save = on_save
        self.included_paths = []
        self.excluded_paths = []

        self.title(f"Edit Exclusions for {backup_dir.path}")
        self.geometry("800x700")

        # Main frame
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.rowconfigure(2, weight=1)
        main_frame.columnconfigure(0, weight=1)

        # Text widget for exclusions
        self.text_exclusions = tk.Text(main_frame, wrap=tk.WORD, height=8)
        self.text_exclusions.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.text_exclusions.insert(tk.END, self.backup_dir.iexclude or "")

        # Frame for buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))

        self.btn_simulate = ttk.Button(button_frame, text="Simulate", command=self.simulate)
        self.btn_simulate.pack(side=tk.LEFT)

        self.btn_save = ttk.Button(button_frame, text="Save", command=self.save)
        self.btn_save.pack(side=tk.RIGHT)

        # Results Frame will contain everything below
        results_frame = ttk.LabelFrame(main_frame, text="Simulation Results", padding="5")
        results_frame.grid(row=2, column=0, sticky="nsew", pady=(5,0))
        results_frame.rowconfigure(0, weight=1)
        results_frame.columnconfigure(0, weight=1)
        
        # Paned window for resizing tree and list views
        paned_window = ttk.PanedWindow(results_frame, orient=tk.VERTICAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        
        # --- Top Pane: TreeView ---
        tree_pane = ttk.Frame(paned_window)
        paned_window.add(tree_pane, weight=1)
        tree_pane.rowconfigure(0, weight=1)
        tree_pane.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_pane, show="tree")
        tree_ysb = ttk.Scrollbar(tree_pane, orient=tk.VERTICAL, command=self.tree.yview)
        tree_xsb = ttk.Scrollbar(tree_pane, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_ysb.set, xscrollcommand=tree_xsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_ysb.grid(row=0, column=1, sticky="ns")
        tree_xsb.grid(row=1, column=0, sticky="ew")

        # --- Bottom Pane: List Views ---
        list_pane = ttk.Frame(paned_window)
        paned_window.add(list_pane, weight=1)
        list_pane.rowconfigure(1, weight=1)
        list_pane.columnconfigure(0, weight=1)
        
        self.lbl_results = ttk.Label(list_pane, text="Click 'Simulate' to see results.")
        self.lbl_results.grid(row=0, column=0, sticky="w", columnspan=2)

        self.text_output = tk.Text(list_pane, wrap=tk.NONE, height=6)
        self.text_output.grid(row=1, column=0, sticky="nsew")
        text_ysb = ttk.Scrollbar(list_pane, orient=tk.VERTICAL, command=self.text_output.yview)
        text_xsb = ttk.Scrollbar(list_pane, orient=tk.HORIZONTAL, command=self.text_output.xview)
        self.text_output.configure(yscrollcommand=text_ysb.set, xscrollcommand=text_xsb.set)
        text_ysb.grid(row=1, column=1, sticky="ns")

        button_frame_lists = ttk.Frame(list_pane)
        button_frame_lists.grid(row=2, column=0, sticky="ew", pady=2)

        self.btn_show_included = ttk.Button(button_frame_lists, text="Show Inclusions", command=self.show_inclusions)
        self.btn_show_included.pack(side=tk.LEFT)
        self.btn_show_excluded = ttk.Button(button_frame_lists, text="Show Exclusions", command=self.show_exclusions)
        self.btn_show_excluded.pack(side=tk.LEFT, padx=5)
        self.btn_show_all = ttk.Button(button_frame_lists, text="Show All", command=self.show_all)
        self.btn_show_all.pack(side=tk.LEFT)
        text_xsb.grid(row=3, column=0, columnspan=2, sticky="ew")

    def _populate_tree(self, parent, data):
        for item, children in sorted(data.items()):
            item_id = self.tree.insert(parent, 'end', text=item, open=False)
            if children:
                self._populate_tree(item_id, children)
    
    def show_inclusions(self):
        self.text_output.delete("1.0", tk.END)
        self.text_output.insert("1.0", "\n".join(self.included_paths))

    def show_exclusions(self):
        self.text_output.delete("1.0", tk.END)
        self.text_output.insert("1.0", "\n".join(self.excluded_paths))

    def show_all(self):
        self.text_output.delete("1.0", tk.END)
        all_paths = sorted(["+ " + p for p in self.included_paths] + ["- " + p for p in self.excluded_paths])
        self.text_output.insert("1.0", "\n".join(all_paths))

    def is_path_excluded(self, rel_path, is_dir, patterns_regex):
        check_path = rel_path
        if is_dir and rel_path and not check_path.endswith('/'):
             check_path += '/'
        
        for regex in patterns_regex:
            if regex.search(check_path):
                return True
        return False

    def simulate(self):
        patterns_text = self.text_exclusions.get("1.0", tk.END).splitlines()
        self.lbl_results.config(text="Simulating...")
        self.update_idletasks()

        self.included_paths = []
        self.excluded_paths = []
        raw_excluded = set()
        included_bytes = 0
        excluded_bytes = 0
        
        root_path = str(self.backup_dir.path)
        patterns_regex = [translate_pattern_to_regex(p) for p in patterns_text if p]
        patterns_regex = [r for r in patterns_regex if r]

        for root, dirs, files in os.walk(root_path, topdown=True):
            all_items = files + dirs
            for item in all_items:
                full_path = os.path.join(root, item)
                rel_path = os.path.relpath(full_path, root_path).replace(os.sep, '/')
                is_dir = os.path.isdir(full_path)

                is_excluded = False
                if self.is_path_excluded(rel_path, is_dir, patterns_regex):
                    is_excluded = True
                else:
                    parent_path = os.path.dirname(rel_path)
                    while parent_path:
                        if self.is_path_excluded(parent_path, True, patterns_regex):
                            is_excluded = True
                            break
                        parent_path = os.path.dirname(parent_path)
                
                if is_excluded:
                    path_to_add = rel_path + '/' if is_dir else rel_path
                    raw_excluded.add(path_to_add)
                    if not is_dir:
                        try:
                            excluded_bytes += os.path.getsize(full_path)
                        except OSError: pass
                elif not is_dir:
                    self.included_paths.append(rel_path)
                    try:
                        included_bytes += os.path.getsize(full_path)
                    except OSError: pass
        
        self.excluded_paths = sorted(list(raw_excluded))
        self.included_paths.sort()
        
        # --- Update UI ---
        def format_bytes(size):
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size < 1024.0: break
                size /= 1024.0
            return f"{size:.2f} {unit}"

        result_text = (
            f"Included: {len(self.included_paths)} files ({format_bytes(included_bytes)}) | "
            f"Excluded: {len(self.excluded_paths)} items ({format_bytes(excluded_bytes)})"
        )
        self.lbl_results.config(text=result_text)

        # --- Populate Tree ---
        self.tree.delete(*self.tree.get_children())
        
        # 1. Find top-most excluded paths
        excluded_set = set(self.excluded_paths)
        top_most_paths = []
        for path in self.excluded_paths:
            parent = os.path.dirname(path.strip('/'))
            # A path is top-most if its parent is not also in the excluded set
            if not parent or (parent + '/') not in excluded_set:
                top_most_paths.append(path)

        # 2. Build tree data starting from top-most paths
        tree_data = {}
        for path in self.excluded_paths:
            for top_path in top_most_paths:
                if path == top_path:
                    tree_data.setdefault(top_path, {})
                    break
                elif path.startswith(top_path):
                    sub_path = path[len(top_path):]
                    node = tree_data.setdefault(top_path, {})
                    for part in sub_path.strip('/').split('/'):
                        if part:
                            node = node.setdefault(part, {})
                    break
        
        self._populate_tree('', tree_data)

        # Set default list view
        self.show_exclusions()

    def save(self):
        self.backup_dir.iexclude = self.text_exclusions.get("1.0", tk.END).strip()
        if self.on_save:
            self.on_save(self.backup_dir)
        self.destroy()