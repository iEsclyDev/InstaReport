"""Reusable Tkinter widgets — ModuleCard, GradientCanvas, LoadingSpinner, tool window, console."""
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable
import re, time

from instareport.ui.theme import (
    BG_DARK, BG_CARD, BG_INPUT, BG_HOVER, FG_PRIMARY, FG_SECONDARY,
    FG_DIM, ACCENT_GREEN, ACCENT_PINK, ACCENT_BLUE, ACCENT_AMBER,
    BORDER, SCROLL_TROUGH, SCROLL_THUMB, TAG_COLORS,
    FONT, H1, H2, H3, BODY, SMALL, MONO, FONT_FAMILY,
    DesignSystem as DS, _make_font,
)
from instareport.utils.constants import TABS, MODULES, STATUS_COL, TAG_PATTERNS
from instareport.core.state import S


class GradientCanvas(tk.Canvas):
    """Canvas with a vertical gradient background."""

    def __init__(self, parent: tk.Widget, color_top: str = BG_DARK, color_bot: str = BG_CARD,
                 height: int = 120, **kw: Any) -> None:
        kw.setdefault("height", height)
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("bd", 0)
        super().__init__(parent, **kw)
        self._top: str = color_top
        self._bot: str = color_bot
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def _draw(self) -> None:
        self.delete("grad")
        w = self.winfo_width() or 1
        h = self.winfo_height() or 1
        for i in range(h):
            r = i / max(h - 1, 1)
            color = self._lerp_hex(self._top, self._bot, r)
            self.create_line(0, i, w, i, fill=color, tags="grad")

    @staticmethod
    def _lerp_hex(c1: str, c2: str, t: float) -> str:
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"


class ModuleCard(tk.Frame):
    """Clickable card for a tool module with icon, label, status badge."""

    def __init__(self, parent: tk.Widget, label: str, status: str, icon: str, desc: str, key: str,
                 callback: Callable[[], Any] | None = None, favorite: bool = False, **kw: Any) -> None:
        kw.setdefault("bg", BG_CARD)
        kw.setdefault("bd", 0)
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("highlightbackground", BORDER)
        super().__init__(parent, **kw)
        self._key: str = key
        self._callback: Callable[[], Any] | None = callback
        self._status: str = status
        self.pack_propagate(False)
        self.config(width=220, height=70)

        inner = tk.Frame(self, bg=BG_CARD, cursor="hand2")
        inner.pack(fill="both", expand=True, padx=10, pady=6)
        inner.bind("<Button-1>", self._on_click)
        inner.bind("<Enter>", lambda e: self.config(highlightbackground=ACCENT_GREEN))
        inner.bind("<Leave>", lambda e: self.config(highlightbackground=BORDER))

        lbl_row = tk.Frame(inner, bg=BG_CARD)
        lbl_row.pack(fill="x")
        star = "★ " if favorite else ""
        lbl = tk.Label(lbl_row, text=f"{icon} {label}", font=H3,
                       fg=FG_PRIMARY, bg=BG_CARD, anchor="w")
        lbl.pack(side="left")
        lbl.bind("<Button-1>", self._on_click)
        badge_clr = STATUS_COL.get(status, FG_DIM)
        badge = tk.Label(lbl_row, text=status, font=SMALL, fg=badge_clr,
                         bg=BG_CARD)
        badge.pack(side="right")
        badge.bind("<Button-1>", self._on_click)

        desc_lbl = tk.Label(inner, text=desc, font=SMALL, fg=FG_DIM,
                            bg=BG_CARD, anchor="w", wraplength=200)
        desc_lbl.pack(fill="x", pady=(2, 0))
        desc_lbl.bind("<Button-1>", self._on_click)

    def _on_click(self, event: Any = None) -> None:
        if self._callback:
            S.operation = self._key
            self._callback()
            self.config(highlightbackground=ACCENT_GREEN)
            self.after(300, lambda: self.config(highlightbackground=BORDER))


class LoadingSpinner(tk.Canvas):
    """Animated spinner using canvas arcs."""

    def __init__(self, parent: tk.Widget, size: int = 24, color: str = ACCENT_GREEN, **kw: Any) -> None:
        kw.setdefault("width", size)
        kw.setdefault("height", size)
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("bd", 0)
        kw.setdefault("bg", BG_DARK)
        super().__init__(parent, **kw)
        self._size: int = size
        self._color: str = color
        self._angle: int = 0
        self._running: bool = False
        self._draw()

    def _draw(self) -> None:
        self.delete("spinner")
        s = self._size
        cx, cy = s / 2, s / 2
        r = s / 2 - 3
        self.create_arc(cx - r, cy - r, cx + r, cy + r,
                        start=self._angle, extent=60,
                        outline=self._color, width=3, tags="spinner",
                        style="arc")

    def start(self) -> None:
        self._running = True
        self._tick()

    def stop(self) -> None:
        self._running = False

    def _tick(self) -> None:
        if not self._running:
            return
        self._angle = (self._angle + 30) % 360
        self._draw()
        self.after(80, self._tick)


class ConsoleWidget(tk.Frame):
    """Scrollable console with ANSI-unaware colored tag system."""

    def __init__(self, parent: tk.Widget, **kw: Any) -> None:
        kw.setdefault("bg", BG_DARK)
        super().__init__(parent, **kw)
        self._text: tk.Text = tk.Text(self, font=MONO, bg=BG_CARD, fg=FG_PRIMARY,
                                      insertbackground=FG_PRIMARY, relief="flat",
                                      bd=0, highlightthickness=0, padx=6, pady=6,
                                      state="disabled", wrap="word",
                                      height=18)
        self._text.pack(side="left", fill="both", expand=True)
        sb = DS.scrollbar(self)
        sb.pack(side="right", fill="y")
        self._text.config(yscrollcommand=sb.set)
        sb.config(command=self._text.yview)
        for tag, clr in TAG_COLORS.items():
            self._text.tag_config(tag, foreground=clr)
        self._text.tag_config("dim", foreground=FG_DIM)
        self._line_count: int = 0

    def write(self, msg: str, tag: str = "dim") -> None:
        self._text.config(state="normal")
        for pattern, t in TAG_PATTERNS:
            if pattern.search(msg):
                tag = t
                break
        self._text.insert("end", msg + "\n", tag)
        self._line_count += 1
        if self._line_count > 2000:
            self._text.delete("1.0", "2.0")
        self._text.see("end")
        self._text.config(state="disabled")

    def clear(self) -> None:
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        self._line_count = 0
        self._text.config(state="disabled")


class LabeledSeparator(tk.Frame):
    """Horizontal line with a text label in the middle."""

    def __init__(self, parent: tk.Widget, text: str = "", **kw: Any) -> None:
        kw.setdefault("bg", BG_DARK)
        super().__init__(parent, **kw)
        self.pack(fill="x", pady=8)
        self.columnconfigure(1, weight=1)
        tk.Label(self, text=f"  {text}  ", font=SMALL, fg=FG_DIM,
                 bg=BG_DARK).grid(row=0, column=0, sticky="w")
        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.grid(row=0, column=1, sticky="ew", padx=(0, 4))


def _tool_win(title: str, w: int, h: int, parent: tk.Widget | None = None) -> tk.Toplevel:
    """Create a themed modal Toplevel."""
    from instareport.utils.helpers import _center_on_parent
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=BG_DARK)
    win.resizable(False, False)
    _center_on_parent(win, parent or win, w, h)
    win.transient(parent)
    win.grab_set()
    return win
