"""Theme system — color palette, fonts, DesignSystem helpers for Tkinter."""
import tkinter as tk
from tkinter import font as tkfont
from typing import Any

# ── Color palette ─────────────────────────────────────────────────────
BG_DARK = "#0D0D0D"
BG_CARD = "#1A1A1A"
BG_INPUT = "#222222"
BG_HOVER = "#2A2A2A"
FG_PRIMARY = "#FFFFFF"
FG_SECONDARY = "#AAAAAA"
FG_DIM = "#666666"
ACCENT_GREEN = "#00E5A0"
ACCENT_PINK = "#F43F7A"
ACCENT_BLUE = "#3B82F6"
ACCENT_AMBER = "#F59E0B"
ACCENT_PURPLE = "#8B5CF6"
BORDER = "#333333"
SCROLL_TROUGH = "#1A1A1A"
SCROLL_THUMB = "#444444"
PROGRESS_BG = "#1A1A1A"
PROGRESS_FG = ACCENT_GREEN
TAG_COLORS = {
    "ok": ACCENT_GREEN, "err": ACCENT_PINK, "proxy": ACCENT_BLUE,
    "sys": ACCENT_AMBER, "warn": "#F97316",
}
TAB_BG = BG_DARK
TAB_FG = FG_SECONDARY
TAB_SEL_BG = BG_CARD
TAB_SEL_FG = ACCENT_GREEN

# ── Font shorthands ───────────────────────────────────────────────────
FONT_FAMILY = "sans-serif"


def _make_font(size: int = 10, bold: bool = False, family: str = FONT_FAMILY) -> tuple[str, int, str]:
    return (family, size, "bold" if bold else "normal")


FONT = _make_font
H1 = _make_font(18, True)
H2 = _make_font(14, True)
H3 = _make_font(12, True)
BODY = _make_font(10)
SMALL = _make_font(8)
MONO = ("monospace", 10)


class DesignSystem:
    """Factory for consistent themed Tkinter widgets."""

    @staticmethod
    def primary_btn(parent: tk.Widget, text: str, command: Any = None, width: int | None = None) -> tk.Button:
        btn = tk.Button(parent, text=text, font=BODY, bg=ACCENT_GREEN,
                        fg=BG_DARK, activebackground="#00CC8A",
                        activeforeground=BG_DARK, relief="flat",
                        bd=0, padx=16, pady=6, cursor="hand2",
                        command=command)
        if width:
            btn.config(width=width)
        return btn

    @staticmethod
    def ghost_btn(parent: tk.Widget, text: str, command: Any = None, width: int | None = None) -> tk.Button:
        btn = tk.Button(parent, text=text, font=BODY, bg=BG_CARD,
                        fg=FG_PRIMARY, activebackground=BG_HOVER,
                        activeforeground=FG_PRIMARY, relief="flat",
                        bd=0, padx=16, pady=6, cursor="hand2",
                        command=command)
        if width:
            btn.config(width=width)
        return btn

    @staticmethod
    def danger_btn(parent: tk.Widget, text: str, command: Any = None, width: int | None = None) -> tk.Button:
        btn = tk.Button(parent, text=text, font=BODY, bg=ACCENT_PINK,
                        fg="#FFFFFF", activebackground="#D63A6A",
                        activeforeground="#FFFFFF", relief="flat",
                        bd=0, padx=16, pady=6, cursor="hand2",
                        command=command)
        if width:
            btn.config(width=width)
        return btn

    @staticmethod
    def label(parent: tk.Widget, text: str, font: tuple = FONT(10), fg: str = FG_PRIMARY, **kw: Any) -> tk.Label:
        return tk.Label(parent, text=text, font=font, fg=fg,
                        bg=BG_DARK, **kw)

    @staticmethod
    def entry(parent: tk.Widget, width: int = 30, show: str | None = None, **kw: Any) -> tk.Entry:
        return tk.Entry(parent, font=BODY, bg=BG_INPUT, fg=FG_PRIMARY,
                        insertbackground=FG_PRIMARY, relief="flat",
                        bd=0, highlightthickness=1,
                        highlightcolor=BORDER, highlightbackground=BORDER,
                        width=width, show=show, **kw)

    @staticmethod
    def combo(parent: tk.Widget, values: list[str], width: int = 28, **kw: Any) -> Any:
        from tkinter import ttk
        cb = ttk.Combobox(parent, values=values, font=BODY, width=width,
                          state="readonly", **kw)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=BG_INPUT,
                        background=BG_CARD, foreground=FG_PRIMARY,
                        arrowcolor=FG_PRIMARY, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER,
                        selectbackground=BG_HOVER, selectforeground=FG_PRIMARY)
        style.map("TCombobox", fieldbackground=[("readonly", BG_INPUT)])
        cb.configure(style="TCombobox")
        return cb

    @staticmethod
    def checkbox(parent: tk.Widget, text: str, variable: tk.BooleanVar, **kw: Any) -> tk.Checkbutton:
        return tk.Checkbutton(parent, text=text, font=BODY, fg=FG_PRIMARY,
                              bg=BG_DARK, selectcolor=BG_CARD,
                              activebackground=BG_DARK,
                              activeforeground=FG_PRIMARY,
                              variable=variable, relief="flat", bd=0,
                              **kw)

    @staticmethod
    def text(parent: tk.Widget, height: int = 10, width: int = 60, **kw: Any) -> tk.Text:
        txt = tk.Text(parent, font=MONO, bg=BG_CARD, fg=FG_PRIMARY,
                      insertbackground=FG_PRIMARY, relief="flat",
                      bd=0, highlightthickness=0, height=height,
                      width=width, padx=8, pady=8, **kw)
        txt.tag_config("ok", foreground=TAG_COLORS["ok"])
        txt.tag_config("err", foreground=TAG_COLORS["err"])
        txt.tag_config("proxy", foreground=TAG_COLORS["proxy"])
        txt.tag_config("sys", foreground=TAG_COLORS["sys"])
        txt.tag_config("warn", foreground=TAG_COLORS["warn"])
        txt.tag_config("dim", foreground=FG_DIM)
        return txt

    @staticmethod
    def stat_card(parent: tk.Widget, label_text: str, value_text: str = "0", accent: str = ACCENT_GREEN,
                  width: int = 160, height: int = 70) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG_CARD, highlightbackground=accent,
                         highlightthickness=1, bd=0, width=width,
                         height=height)
        frame.pack_propagate(False)
        lbl = tk.Label(frame, text=label_text, font=SMALL, fg=FG_DIM,
                       bg=BG_CARD)
        lbl.pack(side="top", anchor="w", padx=8, pady=(6, 0))
        val = tk.Label(frame, text=str(value_text), font=H2,
                       fg=accent, bg=BG_CARD)
        val.pack(side="top", anchor="w", padx=8)
        return frame

    @staticmethod
    def separator(parent: tk.Widget, color: str = BORDER, height: int = 1) -> tk.Frame:
        return tk.Frame(parent, bg=color, height=height, bd=0)

    @staticmethod
    def scrollbar(parent: tk.Widget, orient: str = "vertical") -> tk.Scrollbar:
        return tk.Scrollbar(parent, orient=orient,
                            bg=SCROLL_TROUGH, troughcolor=SCROLL_TROUGH,
                            activebackground=SCROLL_THUMB,
                            highlightbackground=BORDER,
                            bd=0, relief="flat", width=10)
