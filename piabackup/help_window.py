# encoding: utf-8
import tkinter as tk
from tkinter import ttk

import piabackup.common as common


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
        
        self.add_text(text, "Configuration Help\n", "h1")
        
        self.add_text(text, "General Settings\n", "h2")
        self.add_text(text, "• Start application on Windows logon: Automatically starts the backup agent in the background. However! It is better to use the Windows Task Scheduler to run PiaBackup with elevated privileges so restic can make use of Windows VSS snapshots for cleaner backups.\n", "body")
        self.add_text(text, "• Enable automatic backup path discovery: If enabled, the application will periodically (every 24 hours) scan for known important directories (like game saves, documents, etc.) and automatically add them to your backup list with 'auto' enabled status. You will be notified via a toast message when new paths are added. This is functionally the same as the Auto Detect button.\n", "body")
        self.add_text(text, "• Make vanished root folders' latest backups permanent: If a configured backup directory is missing (e.g. deleted or external drive disconnected), the last successful snapshot for that directory is automatically tagged as 'permanent'. This prevents the pruning process from deleting your last good backup of that data due to aging.\n", "body")
        self.add_text(text, "• Prescan File Limit: Maximum number of files to scan to decide whether the backup needs to run (avoids hogging the system due to unnecessary VSS snapshots). Set to 0 to disable prescan.\n", "body")
        
        self.add_text(text, "\nRestic Configuration\n", "h2")
        self.add_text(text, "PiaBackup uses its own installations of restic and rclone so it runs against pre-defined versions of those tools and we can be sure of their exact behavior. Those tools are installed in '%USERPROFILE%\\AppData\\Local\\py_apps\\piabackup\\dl'. When setting up rclone config, you might want to use the same version installed in that path (maybe add that path to your user Path env var).\n\n", "body")
        self.add_text(text, "• Repository: The location where backups are stored. Can be a local folder (ie. 'local:D:\\ResticRepo1') or a remote location supported by rclone (ie. 'rclone:gdrive:.restic_repos/1' where 'gdrive' is a rclone config name that you need to configure and test outside of this app.).\n", "body")
        self.add_text(text, "• Full Check Frequency: How often to verify the integrity of all data in the repository. It does the following in the listed order:\n", "body")
        self.add_text(text, "  • Delete restic's local cache.\n", "body")
        self.add_text(text, "  • Forces restic to run a full check on the repository. Restic will download the complete repository via network in that step so it can take a long time to finish. This should work as a bitrot check on the repository data.\n", "body")
        self.add_text(text, "• Prune Frequency: How often to remove old/unused data from the repository to free up space.\n", "body")
        self.add_text(text, "• Enable Bitrot Detection: Part of the pruning mechanism. Bitrot checks are done on the repository metadata just before each prune and prevent prune execution if something is found to avoid losing good data to bitrot. Beware that this is a best-effort solution, not a perfect catch-all. Part of the bitrot detection is forcing restic to do a full client data read, which implicitly works as a bitrot check on the client.\n", "body")
        
        self.add_text(text, "\nSnapshot Management\n", "h2")
        self.add_text(text, "• You can browse snapshots by right-clicking a backup directory and selecting 'Browse'.\n", "body")
        self.add_text(text, "• In the snapshot list, right-click a snapshot to toggle the 'permanent' tag. Snapshots tagged as 'permanent' are excluded from pruning (retention policy), meaning they will be kept indefinitely.\n", "body")
        self.add_text(text, "• However, be aware that the restic command line tool itself doesn't care about tags when pruning unless explicitly told to do so. Keep that in mind when manually managing your repo.\n", "body")

        self.add_text(text, "\nWarnings\n", "h2")
        self.add_text(text, "• PiaBackup can be configured to run restic with the --no-lock option. You probably shouldn't touch this unless you know exactly what you are doing and what this program's code is doing!!!\n", "body")

        self.add_text(text, "\nBackup Directories\n", "h2")
        self.add_text(text, "• Add folders you want to back up.\n", "body")
        self.add_text(text, "• You can set individual frequencies for each folder.\n", "body")
        self.add_text(text, "• Each folder uses its own path as a tag. That makes restic treat them as independent backups and deleting one of those folders completely won't make you automatically lose it eventually to the prune gods.\n", "body")
        
        self.add_text(text, "\nSetting up a Local Repository\n", "h2")
        self.add_text(text, "1. Create a folder on your external drive or secondary disk (e.g., D:\\Backups).\n", "body")
        self.add_text(text, "2. In the Settings > Repository field, enter the path (e.g., local:D:\\Backups).\n", "body")
        self.add_text(text, "3. Click 'Test Connection'.\n", "body")
        self.add_text(text, "4. If the repository is not initialized, you will be asked to initialize it. Click Yes.\n", "body")
        self.add_text(text, "5. You will be prompted to set a password. Remember this password! Without it, your backups are inaccessible.\n", "body")
        
        self.add_text(text, "\nSetting up a Remote Repository (via rclone)\n", "h2")
        self.add_text(text, "1. Ensure rclone is installed (the app attempts to download it if missing).\n", "body")
        self.add_text(text, "2. Open a command prompt/terminal and run: rclone config\n", "body")
        self.add_text(text, "3. Follow the interactive setup to configure your remote (e.g., Google Drive, S3, B2). Name it (e.g., 'gdrive').\n", "body")
        self.add_text(text, "4. In the Settings > Repository field, enter the rclone path: rclone:remote_name:bucket_name/path\n", "body")
        self.add_text(text, "   Example: rclone:gdrive:backups/piarepo\n", "body")
        self.add_text(text, "5. Click 'Test Connection' and follow initialization steps if necessary.\n", "body")
        
        text.config(state=tk.DISABLED)
        
        common.center_window(self, 700, 600)

    def add_text(self, widget, text, tag):
        widget.insert(tk.END, text, tag)
