import tkinter as tk
from tkinter import font, filedialog
import os

class TkLess:
    def __init__(self, root:tk.Tk, filepath=None):
        self.root = tk.Toplevel(root) if root else tk.Tk()
        self.root.title("TkLess (Press 'Shift+F' to toggle Follow Mode)")
        self.root.geometry("900x600")

        # --- State Variables ---
        self.filepath = filepath
        self.lines = []
        self.line_height = 0
        self.visible_lines = 0
        self.total_lines = 0
        self.top_line_index = 0
        
        # Tail / Follow Logic
        self.following = False      # Are we currently 'tailing'?
        self.fullscreen = False
        self.last_file_size = 0     # To track file growth
        self.poll_interval = 500    # Check file every 500ms

        # Styling
        self.bg_color = "#1e1e1e"
        self.fg_color = "#d4d4d4"
        self.info_color = "#007acc" # Color for status bar/info
        self.font_style = font.Font(family="Courier New", size=10)

        self._setup_ui()
        self._bind_events()

        # Start the monitoring loop
        self.root.after(self.poll_interval, self.monitor_file)

        if self.filepath:
            self.load_file(self.filepath)
        else:
            self.open_file_dialog()

        self.root.lift()
        self.root.focus_force()

    def _setup_ui(self):
        # 1. Main Frame
        self.frame = tk.Frame(self.root, bg=self.bg_color)
        self.frame.pack(fill="both", expand=True)

        # 2. Status Bar (To show "Following" status)
        self.status_bar = tk.Label(
            self.root, 
            text="-- Idle --", 
            bg=self.info_color, 
            fg="white", 
            anchor="w",
            font=("Arial", 9, "bold")
        )
        self.status_bar.pack(side="bottom", fill="x")

        # 3. Canvas for text
        self.canvas = tk.Canvas(self.frame, bg=self.bg_color, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        # 4. Scrollbar
        self.scrollbar = tk.Scrollbar(self.frame, command=self.on_scroll)
        self.scrollbar.pack(side="right", fill="y")
        
        # Calculate line height
        dummy_text = self.canvas.create_text(0, 0, text="Tg", font=self.font_style, anchor="nw")
        bbox = self.canvas.bbox(dummy_text)
        self.line_height = (bbox[3] - bbox[1]) + 2 # +2 padding
        self.canvas.delete(dummy_text)

    def _bind_events(self):
        self.canvas.bind("<Configure>", self.on_resize)
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind_all("<Button-4>", self.on_mousewheel)
        self.canvas.bind_all("<Button-5>", self.on_mousewheel)
        
        # Navigation
        self.root.bind("<Up>", lambda e: self.scroll_lines(-1))
        self.root.bind("<Down>", lambda e: self.scroll_lines(1))
        self.root.bind("<Prior>", lambda e: self.scroll_pages(-1))
        self.root.bind("<Next>", lambda e: self.scroll_pages(1))
        self.root.bind("<Home>", lambda e: self.jump_to(0))
        self.root.bind("<End>", lambda e: self.jump_to_end())
        
        # Toggle Follow Mode
        self.root.bind("<F>", lambda e: self.toggle_follow()) # Shift+F like 'less'
        self.root.bind("<f>", lambda e: self.toggle_fullscreen())
        
        self.root.bind("<q>", lambda e: self.root.destroy())
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def open_file_dialog(self):
        path = filedialog.askopenfilename()
        if path:
            self.load_file(path)

    def load_file(self, path):
        self.filepath = path
        self.root.title(f"TkLess - {os.path.basename(path)}")
        
        # Reset
        self.lines = []
        self.last_file_size = 0
        
        # Initial Read
        if os.path.exists(path):
            self.last_file_size = os.path.getsize(path)
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                self.lines = f.read().splitlines()
        
        self.total_lines = len(self.lines)
        self.update_status()
        self.redraw()
        self.update_scrollbar()

    def toggle_follow(self):
        self.following = not self.following
        if self.following:
            self.jump_to_end()
        self.update_status()

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)

    def update_status(self):
        mode = "FOLLOWING (Tail)" if self.following else "Static (Press F to follow)"
        line_info = f"Lines: {self.total_lines}"
        self.status_bar.config(text=f" {mode} | {line_info}")
        
        # Change status bar color based on mode
        bg = "#b30000" if self.following else self.info_color
        self.status_bar.config(bg=bg)

    def monitor_file(self):
        """ Checks if file has grown. If so, reads new lines. """
        if self.filepath and os.path.exists(self.filepath):
            current_size = os.path.getsize(self.filepath)
            
            # If file grew
            if current_size > self.last_file_size:
                try:
                    with open(self.filepath, 'r', encoding='utf-8', errors='replace') as f:
                        f.seek(self.last_file_size)
                        new_content = f.read()
                        new_lines = new_content.splitlines()
                        
                        # Handle edge case where last line didn't have \n yet
                        if self.lines and not new_content.startswith('\n') and self.last_file_size > 0:
                             # Append to the last line instead of new line
                             # (Simplification: just add new lines for now to avoid complexity)
                             pass

                        if new_lines:
                            self.lines.extend(new_lines)
                            self.total_lines = len(self.lines)
                            self.last_file_size = current_size
                            
                            if self.following:
                                self.jump_to_end()
                            else:
                                # Just update scrollbar logic without moving view
                                self.update_scrollbar()
                                self.update_status()
                except Exception as e:
                    print(f"Error reading file update: {e}")

        # Schedule next check
        self.root.after(self.poll_interval, self.monitor_file)

    def redraw(self):
        self.canvas.delete("all")
        canvas_height = self.canvas.winfo_height()
        if canvas_height <= 1: return
        
        self.visible_lines = canvas_height // self.line_height + 1
        start = self.top_line_index
        end = min(self.total_lines, start + self.visible_lines)
        
        y = 0
        for i in range(start, end):
            self.canvas.create_text(
                10, y, 
                text=self.lines[i], 
                fill=self.fg_color, 
                anchor="nw", 
                font=self.font_style
            )
            y += self.line_height

    def update_scrollbar(self):
        if self.total_lines == 0: return
        start_ratio = self.top_line_index / self.total_lines
        end_ratio = (self.top_line_index + self.visible_lines) / self.total_lines
        self.scrollbar.set(start_ratio, end_ratio)

    def on_scroll(self, *args):
        # Disable follow mode if user manually scrolls
        if self.following:
            self.following = False
            self.update_status()

        if args[0] == 'moveto':
            ratio = float(args[1])
            self.top_line_index = int(ratio * self.total_lines)
            self.redraw()
        elif args[0] == 'scroll':
            self.scroll_lines(int(args[1]))

    def on_mousewheel(self, event):
        # Disable follow mode if user manually scrolls
        if self.following:
            self.following = False
            self.update_status()

        if event.num == 5 or event.delta < 0:
            self.scroll_lines(3)
        if event.num == 4 or event.delta > 0:
            self.scroll_lines(-3)

    def scroll_lines(self, count):
        new_top = self.top_line_index + count
        new_top = max(0, min(new_top, self.total_lines - self.visible_lines + 1))
        if new_top != self.top_line_index:
            self.top_line_index = new_top
            self.redraw()
            self.update_scrollbar()

    def scroll_pages(self, direction):
        self.scroll_lines(direction * (self.visible_lines - 1))

    def jump_to(self, line_index):
        self.following = False # Manual jump kills follow mode
        self.update_status()
        self.top_line_index = max(0, min(line_index, self.total_lines - 1))
        self.redraw()
        self.update_scrollbar()

    def jump_to_end(self):
        # Logic to jump to the very bottom
        target = self.total_lines - self.visible_lines + 1
        self.top_line_index = max(0, target)
        self.redraw()
        self.update_scrollbar()
    
    def on_resize(self, event):
        self.redraw()
        self.update_scrollbar()
    
    def run(self):
        self.root.mainloop()
