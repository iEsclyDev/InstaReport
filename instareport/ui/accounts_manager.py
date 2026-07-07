"""Accounts Manager — Toplevel for listing, adding, editing, importing/exporting accounts."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Any
import json, os

from instareport.ui.theme import (
    BG_DARK, BG_CARD, BG_INPUT, FG_PRIMARY, FG_SECONDARY, FG_DIM,
    ACCENT_GREEN, ACCENT_PINK, BORDER,
    FONT, H1, H2, H3, BODY, SMALL, MONO,
    DesignSystem as DS,
)
from instareport.ui.widgets import _tool_win
from instareport.core.state import S, ACCOUNTS_LOCK
from instareport.core.config import save_config
from instareport.utils.logging import log


class AccountsManager:
    """Accounts management window."""

    def __init__(self, parent: tk.Widget) -> None:
        self.win: tk.Toplevel = _tool_win("Accounts Manager", 650, 480, parent)
        self._tree: ttk.Treeview
        self._build_ui()

    def _build_ui(self) -> None:
        DS.label(self.win, "Accounts Manager", font=H2).pack(pady=(10, 4))

        toolbar = tk.Frame(self.win, bg=BG_DARK)
        toolbar.pack(fill="x", padx=10, pady=4)
        DS.primary_btn(toolbar, "+ Add", command=self._add_acct,
                       width=8).pack(side="left", padx=2)
        DS.ghost_btn(toolbar, "Edit", command=self._edit_acct,
                     width=8).pack(side="left", padx=2)
        DS.danger_btn(toolbar, "Delete", command=self._delete_acct,
                      width=8).pack(side="left", padx=2)
        DS.ghost_btn(toolbar, "Import", command=self._import_accts,
                     width=8).pack(side="right", padx=2)
        DS.ghost_btn(toolbar, "Export", command=self._export_accts,
                     width=8).pack(side="right", padx=2)

        frame = tk.Frame(self.win, bg=BG_CARD)
        frame.pack(fill="both", expand=True, padx=10, pady=6)
        self._tree = ttk.Treeview(frame, columns=("user", "pw"),
                                  show="headings", height=14)
        self._tree.heading("user", text="Username")
        self._tree.heading("pw", text="Password")
        self._tree.column("user", width=250)
        self._tree.column("pw", width=250)
        self._tree.pack(side="left", fill="both", expand=True)
        sb = DS.scrollbar(frame)
        sb.pack(side="right", fill="y")
        self._tree.config(yscrollcommand=sb.set)
        sb.config(command=self._tree.yview)
        self._refresh()

    def _refresh(self) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)
        with ACCOUNTS_LOCK:
            for u, pw in S.accounts[:]:
                self._tree.insert("", "end", values=(u, "*" * len(pw)))

    def _get_selected(self) -> tuple[int, str] | None:
        sel = self._tree.selection()
        if not sel:
            log("No account selected", "warn")
            return None
        vals = self._tree.item(sel[0], "values")
        if not vals:
            return None
        idx = self._tree.index(sel[0])
        return idx, vals[0]

    def _add_acct(self) -> None:
        win = tk.Toplevel(self.win)
        win.title("Add Account")
        win.configure(bg=BG_DARK)
        win.resizable(False, False)
        DS.label(win, "Username:", font=BODY).grid(row=0, column=0, padx=8, pady=6, sticky="e")
        u_e = DS.entry(win, width=30)
        u_e.grid(row=0, column=1, padx=8, pady=6)
        DS.label(win, "Password:", font=BODY).grid(row=1, column=0, padx=8, pady=6, sticky="e")
        p_e = DS.entry(win, width=30, show="*")
        p_e.grid(row=1, column=1, padx=8, pady=6)

        def save() -> None:
            u = u_e.get().strip()
            pw = p_e.get().strip()
            if not u or not pw:
                return
            with ACCOUNTS_LOCK:
                S.accounts.append((u, pw))
            save_config()
            self._refresh()
            log(f"Account {u} added ({len(S.accounts)} total)", "ok")
            win.destroy()

        DS.primary_btn(win, "Add", command=save).grid(row=2, column=0, columnspan=2, pady=10)

    def _edit_acct(self) -> None:
        sel = self._get_selected()
        if not sel:
            return
        idx, username = sel
        win = tk.Toplevel(self.win)
        win.title(f"Edit {username}")
        win.configure(bg=BG_DARK)
        win.resizable(False, False)
        DS.label(win, "Username:", font=BODY).grid(row=0, column=0, padx=8, pady=6, sticky="e")
        u_e = DS.entry(win, width=30)
        u_e.insert(0, username)
        u_e.grid(row=0, column=1, padx=8, pady=6)
        DS.label(win, "Password:", font=BODY).grid(row=1, column=0, padx=8, pady=6, sticky="e")
        p_e = DS.entry(win, width=30, show="*")
        p_e.grid(row=1, column=1, padx=8, pady=6)

        def save() -> None:
            u = u_e.get().strip()
            pw = p_e.get().strip()
            if not u or not pw:
                return
            with ACCOUNTS_LOCK:
                if idx < len(S.accounts):
                    S.accounts[idx] = (u, pw)
            save_config()
            self._refresh()
            log(f"Account {u} updated", "ok")
            win.destroy()

        DS.primary_btn(win, "Save", command=save).grid(row=2, column=0, columnspan=2, pady=10)

    def _delete_acct(self) -> None:
        sel = self._get_selected()
        if not sel:
            return
        idx, username = sel
        if not messagebox.askyesno("Confirm", f"Delete {username}?"):
            return
        with ACCOUNTS_LOCK:
            if idx < len(S.accounts):
                S.accounts.pop(idx)
        save_config()
        self._refresh()
        log(f"Account {username} deleted", "ok")

    def _import_accts(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Text/JSON", "*.txt *.json *.csv")])
        if not path:
            return
        count = 0
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read().strip()
            if path.endswith(".json"):
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, (list, tuple)) and len(item) >= 2:
                            with ACCOUNTS_LOCK:
                                S.accounts.append((item[0].strip(), item[1].strip()))
                            count += 1
                        elif isinstance(item, dict):
                            u = item.get("user") or item.get("username") or ""
                            pw = item.get("pw") or item.get("password") or ""
                            if u and pw:
                                with ACCOUNTS_LOCK:
                                    S.accounts.append((u.strip(), pw.strip()))
                                count += 1
                elif isinstance(data, dict):
                    for u, pw in data.items():
                        with ACCOUNTS_LOCK:
                            S.accounts.append((u.strip(), pw.strip()))
                        count += 1
            else:
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split(":")
                    if len(parts) >= 2:
                        with ACCOUNTS_LOCK:
                            S.accounts.append((parts[0].strip(), parts[1].strip()))
                        count += 1
            save_config()
            self._refresh()
            log(f"Imported {count} accounts", "ok")
        except Exception as e:
            log(f"Import error: {e}", "err")

    def _export_accts(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                            filetypes=[("Text", "*.txt"), ("JSON", "*.json")])
        if not path:
            return
        try:
            with ACCOUNTS_LOCK:
                if path.endswith(".json"):
                    data = {u: pw for u, pw in S.accounts}
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                else:
                    with open(path, "w", encoding="utf-8") as f:
                        for u, pw in S.accounts:
                            f.write(f"{u}:{pw}\n")
            log(f"Exported {len(S.accounts)} accounts to {path}", "ok")
        except Exception as e:
            log(f"Export error: {e}", "err")
