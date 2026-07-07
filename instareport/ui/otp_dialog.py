"""OTP / 2FA Code Entry Dialog."""
import tkinter as tk
from typing import Any

from instareport.ui.theme import (
    BG_DARK, BG_CARD, BG_INPUT, FG_PRIMARY, FG_SECONDARY, FG_DIM,
    ACCENT_GREEN, ACCENT_PINK, ACCENT_BLUE, BORDER,
    FONT, H1, H2, H3, BODY, SMALL, MONO,
    DesignSystem as DS,
)
from instareport.ui.widgets import _tool_win
from instareport.core.otp import OTP
from instareport.utils.logging import log


def open_otp_dialog(parent: tk.Widget) -> None:
    """Open a dialog showing pending 2FA requests and allowing code entry."""
    win = _tool_win("2FA Bypass - Pending Requests", 500, 350, parent)
    DS.label(win, "Pending 2FA Requests", font=H2).pack(pady=(10, 4))
    frame = tk.Frame(win, bg=BG_CARD)
    frame.pack(fill="both", expand=True, padx=10, pady=6)
    cols = ("Key", "Status")
    tree = ttk.Treeview(frame, columns=cols, show="headings", height=8)
    tree.heading("Key", text="Request Key")
    tree.heading("Status", text="Status")
    tree.column("Key", width=300)
    tree.column("Status", width=100)
    tree.pack(side="left", fill="both", expand=True)
    sb = DS.scrollbar(frame)
    sb.pack(side="right", fill="y")
    tree.config(yscrollcommand=sb.set)
    sb.config(command=tree.yview)

    DS.label(win, "Enter 2FA Code:", font=BODY).pack(pady=(8, 2))
    code_e = DS.entry(win, width=16)
    code_e.pack(pady=2)

    def submit() -> None:
        code = code_e.get().strip()
        if not code:
            return
        sel = tree.selection()
        if sel:
            key = tree.item(sel[0], "values")[0]
            OTP.submit(key, code)
            log(f"[OTP] Submitted code for {key}", "ok")
            tree.item(sel[0], values=(key, "submitted"))
            code_e.delete(0, "end")
        else:
            log("[OTP] Select a request from the list", "warn")

    DS.primary_btn(win, "Submit Code", command=submit).pack(pady=6)
    DS.label(win, "Waiting for 2FA requests from running sessions…",
             font=SMALL, fg=FG_DIM).pack()
