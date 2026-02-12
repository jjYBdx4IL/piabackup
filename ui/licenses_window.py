import os
import sys
import json
import tkinter as tk
import webbrowser

class LicensesWindow:
    def __init__(self, root, extra_licenses=None):
        self.window = tk.Toplevel(root)
        self.window.title("Open Source Licenses")
        self.window.geometry("700x600")
        
        # Locate licenses.json
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_path, 'licenses.json')
        
        # Main container
        main_frame = tk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(main_frame)
        scrollbar = tk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        
        canvas_frame = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        def on_canvas_configure(event):
            canvas.itemconfig(canvas_frame, width=event.width)
        canvas.bind("<Configure>", on_canvas_configure)
        
        def _on_mousewheel(event):
            x = self.window.winfo_pointerx()
            y = self.window.winfo_pointery()
            widget = self.window.winfo_containing(x, y)
            if isinstance(widget, tk.Text) and widget.yview() != (0.0, 1.0):
                widget.yview_scroll(int(-1*(event.delta/120)), "units")
            else:
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.window.bind("<MouseWheel>", _on_mousewheel)

        # Header disclaimer
        disclaimer_text = (
            "This license list is auto-generated and might contain dependencies that aren't strictly necessary "
            "because they are only involved in building the final package and not part of the distribution.\n\n"
            "Also, the source code of dependencies is usually accessible via the included URLs. "
            "The referenced project homepages should be treated as the authoritative source for licensing."
        )
        tk.Label(scrollable_frame, text=disclaimer_text, justify=tk.LEFT, wraplength=650, fg="#444", padx=10, pady=10, font=("Segoe UI", 9)).pack(fill=tk.X)

        # Load and display licenses
        licenses = []
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    licenses = json.load(f)
            except Exception as e:
                tk.Label(scrollable_frame, text=f"Error parsing licenses.json: {e}", fg="red").pack(padx=10, pady=10)
        
        if getattr(sys, 'frozen', False):
            licenses.append({
                "Name": "Python",
                "Version": sys.version.split()[0],
                "License": "PSF",
                "LicenseText": sys.copyright,
                "URL": "https://www.python.org/",
                "Author": "Python Software Foundation"
            })

        if extra_licenses:
            licenses.extend(extra_licenses)

        if licenses:
            # Sort by name
            licenses.sort(key=lambda x: x.get('Name', '').lower())

            for pkg in licenses:
                self.create_license_entry(scrollable_frame, pkg)
        elif not os.path.exists(json_path):
            tk.Label(scrollable_frame, text=f"licenses.json not found at:\n{json_path}", fg="red").pack(padx=10, pady=10)

    def create_license_entry(self, parent, pkg):
        frame = tk.Frame(parent, borderwidth=1, relief="solid")
        frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Header
        header_frame = tk.Frame(frame)
        header_frame.pack(fill=tk.X, padx=5, pady=5)
        
        name = pkg.get('Name', 'Unknown')
        version = pkg.get('Version', '')
        license_name = pkg.get('License', 'Unknown')
        
        title_text = f"{name} {version}"
        tk.Label(header_frame, text=title_text, font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        tk.Label(header_frame, text=f"[{license_name}]", fg="gray").pack(side=tk.LEFT, padx=5)
        
        btn_text = tk.StringVar(value="Show License")
        btn = tk.Button(header_frame, textvariable=btn_text)
        btn.pack(side=tk.RIGHT)
        
        # Content (hidden)
        content_frame = tk.Frame(frame)
        
        # Metadata
        url = pkg.get('URL')
        if url and url != 'UNKNOWN':
            url_frame = tk.Frame(content_frame)
            url_frame.pack(anchor="w", padx=5, pady=1)
            tk.Label(url_frame, text="URL: ", fg="#333").pack(side=tk.LEFT)
            lbl_link = tk.Label(url_frame, text=url, fg="blue", cursor="hand2")
            lbl_link.pack(side=tk.LEFT)
            lbl_link.bind("<Button-1>", lambda e: webbrowser.open(url))

        author = pkg.get('Author')
        if author and author != 'UNKNOWN':
            tk.Label(content_frame, text=f"Author: {author}", fg="#333").pack(anchor="w", padx=5, pady=1)
            
        # License Text
        lic_text = pkg.get('LicenseText', '')
        if lic_text and lic_text != 'UNKNOWN':
            text_area = tk.Text(content_frame, height=10, font=("Consolas", 9), wrap=tk.WORD)
            text_area.insert(tk.END, lic_text)
            text_area.config(state=tk.DISABLED)
            text_area.pack(fill=tk.X, padx=5, pady=5)
        else:
            tk.Label(content_frame, text="No license text available.", font=("Segoe UI", 9, "italic")).pack(anchor="w", padx=5, pady=5)

        def toggle():
            if content_frame.winfo_ismapped():
                content_frame.pack_forget()
                btn_text.set("Show License")
            else:
                content_frame.pack(fill=tk.X, padx=5, pady=0)
                btn_text.set("Hide License")
        
        btn.config(command=toggle)

    def lift(self):
        self.window.lift()
        self.window.focus_force()
    
    def winfo_exists(self):
        return self.window.winfo_exists()