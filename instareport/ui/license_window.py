"""License Window — activation dialog with HWID-based validation."""
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Any

from instareport.ui.theme import (
    BG_DARK, BG_CARD, BG_INPUT, FG_PRIMARY, FG_SECONDARY, FG_DIM,
    ACCENT_GREEN, ACCENT_PINK, BORDER,
    FONT, H1, H2, H3, BODY, SMALL, MONO,
    DesignSystem as DS,
)
from instareport.ui.widgets import _tool_win, LoadingSpinner
from instareport.core.license import LS
from instareport.utils.logging import dlog


class LicenseWindow:
    """License activation Toplevel."""

    def __init__(self, parent: tk.Widget, on_activate: Callable[[], Any] | None = None) -> None:
        self._parent: tk.Widget = parent
        self._on_activate: Callable[[], Any] | None = on_activate
        self.win: tk.Toplevel = tk.Toplevel(parent)
        self._key_e: tk.Entry
        self._spinner: LoadingSpinner
        self.win.title("Activate License")
        self.win.configure(bg=BG_DARK)
        self.win.resizable(False, False)
        from instareport.utils.helpers import _center_on_parent
        _center_on_parent(self.win, parent or self.win, 460, 300)
        self.win.transient(parent)
        self.win.grab_set()
        self._build_ui()

    def _build_ui(self) -> None:
        DS.label(self.win, "License Activation", font=H1).pack(pady=(20, 4))
        DS.label(self.win, "Enter your license key to activate InstaReport",
                 font=BODY, fg=FG_SECONDARY).pack(pady=(0, 12))
        DS.label(self.win, "License Key:", font=BODY).pack()
        self._key_e = DS.entry(self.win, width=40)
        self._key_e.pack(pady=4)
        self._key_e.focus_set()
        self._spinner = LoadingSpinner(self.win, size=20)
        self._spinner.pack(pady=6)
        self._spinner.pack_forget()
        DS.primary_btn(self.win, "Activate", command=self._activate).pack(pady=10)
        DS.label(self.win, "or", font=SMALL, fg=FG_DIM).pack()
        DS.ghost_btn(self.win, "Skip for now (limited mode)",
                     command=self._skip).pack(pady=4)

    def _activate(self) -> None:
        code = self._key_e.get().strip()
        if not code:
            messagebox.showwarning("Input", "Please enter a license key")
            return
        self._spinner.pack(pady=6)
        self._spinner.start()
        self.win.update()
        ok, msg = LS.validate(code)
        self._spinner.stop()
        self._spinner.pack_forget()
        if ok:
            LS.save(code)
            messagebox.showinfo("Activated", msg)
            self.win.destroy()
            if self._on_activate:
                self._on_activate()
        else:
            messagebox.showerror("Activation Failed", msg)

    def _skip(self) -> None:
        self.win.destroy()
        if self._on_activate:
            self._on_activate()
