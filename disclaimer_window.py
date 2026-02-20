# encoding: utf-8
import tkinter as tk
from tkinter import ttk

import piabackup.common as common
from piabackup.config import Config


class DisclaimerWindow(tk.Toplevel):
    def __init__(self, parent, on_accept, on_refuse):
        super().__init__(parent)
        self.title("Disclaimer")
        self.on_accept = on_accept
        self.on_refuse = on_refuse
        
        self.protocol("WM_DELETE_WINDOW", self.on_refuse)
        
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        text = ("DISCLAIMER OF WARRANTY\n\n"
                "THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY APPLICABLE LAW. "
                "EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT HOLDERS AND/OR OTHER PARTIES "
                "PROVIDE THE PROGRAM \"AS IS\" WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESSED OR IMPLIED, "
                "INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE. "
                "THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM IS WITH YOU. "
                "SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF ALL NECESSARY SERVICING, REPAIR OR CORRECTION.\n\n"
                "IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING WILL ANY COPYRIGHT HOLDER, "
                "OR ANY OTHER PARTY WHO MODIFIES AND/OR CONVEYS THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES, "
                "INCLUDING ANY GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE USE OR INABILITY TO USE THE PROGRAM "
                "(INCLUDING BUT NOT LIMITED TO LOSS OF DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD PARTIES "
                "OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER PROGRAMS), EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.\n\n"
                "FOR ALL I CARE CONSIDER THIS SOFTWARE A DATA CORRUPTION SIMULATOR AND NOTHING ELSE, IT'S YOUR CHOICE TO USE IT AS A BACKUP "
                "SOLUTION OR NOT, BUT DON'T COME CRYING TO ME IF YOU LOSE YOUR DATA BECAUSE YOU DECIDED TO TRUST THIS SOFTWARE DESPITE THE FACT "
                "THAT IT'S PROVIDED WITHOUT ANY KIND OF WARRANTY.")
        
        lbl = tk.Label(frame, text=text, wraplength=500, justify=tk.LEFT)
        lbl.pack(pady=(0, 20))
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)
        
        ttk.Button(btn_frame, text="I Accept", command=self.accept).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Refuse", command=self.on_refuse).pack(side=tk.RIGHT)
        
        common.center_window(self, 550, 450)

    def accept(self):
        cfg = Config()
        cfg.disclaimer_accepted = True
        cfg.save()
        self.destroy()
        if self.on_accept:
            self.on_accept()