"""Plugin Manager — treeview listing all plugins with toggle, refresh, and import controls."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Any

from instareport.ui.theme import (
    BG_DARK, BG_CARD, BG_INPUT, FG_PRIMARY, FG_SECONDARY, FG_DIM,
    ACCENT_GREEN, ACCENT_PINK, ACCENT_BLUE, BORDER,
    FONT, H1, H2, H3, BODY, SMALL, MONO,
    DesignSystem as DS,
)
from instareport.ui.widgets import _tool_win
from instareport.utils.logging import log
from instareport.plugins.loader import (
    get_all_plugins, set_plugin_enabled, discover_plugins,
    get_flow_map, import_plugin_file,
)


class PluginManager:
    """Plugin management window with enable/disable toggles and external import."""

    def __init__(self, parent: tk.Widget) -> None:
        self.win: tk.Toplevel = _tool_win("Plugin Manager", 720, 540, parent)
        self._tree: ttk.Treeview
        self._build_ui()

    def _build_ui(self) -> None:
        DS.label(self.win, "Plugin Manager", font=H2).pack(pady=(10, 4))

        # Settings controls (plugin directory, backup/restore)
        settings_frame = tk.Frame(self.win, bg=BG_CARD, relief="flat", bd=1)
        settings_frame.pack(fill="x", padx=10, pady=2)
        tk.Label(settings_frame, text="Plugin Directory:", font=SMALL,
                 fg=FG_DIM, bg=BG_CARD).pack(side="left", padx=(8, 4))
        self._plugin_dir_var = tk.StringVar(value=self._get_current_plugin_dir())
        dir_e = tk.Entry(settings_frame, textvariable=self._plugin_dir_var,
                         width=40, bg=BG_INPUT, fg=FG_PRIMARY,
                         insertbackground=FG_PRIMARY, relief="flat", font=FONT(9))
        dir_e.pack(side="left", padx=2, fill="x", expand=True)
        DS.ghost_btn(settings_frame, "Browse...", command=self._browse_plugin_dir,
                     width=9).pack(side="left", padx=2)
        DS.primary_btn(settings_frame, "Set", command=self._set_plugin_dir,
                       width=5).pack(side="left", padx=2)

        backup_frame = tk.Frame(self.win, bg=BG_DARK)
        backup_frame.pack(fill="x", padx=10, pady=2)
        DS.ghost_btn(backup_frame, "Backup Config", command=self._backup_config,
                     width=14).pack(side="left", padx=2)
        DS.ghost_btn(backup_frame, "Restore Config", command=self._restore_config,
                     width=14).pack(side="left", padx=2)

        toolbar = tk.Frame(self.win, bg=BG_DARK)
        toolbar.pack(fill="x", padx=10, pady=4)
        DS.primary_btn(toolbar, "Refresh", command=self._refresh,
                       width=10).pack(side="left", padx=2)
        DS.ghost_btn(toolbar, "Import .py", command=self._import_plugin,
                     width=10).pack(side="left", padx=2)
        DS.ghost_btn(toolbar, "Toggle", command=self._toggle_selected,
                     width=10).pack(side="left", padx=2)
        DS.danger_btn(toolbar, "Disable All", command=self._disable_all,
                      width=10).pack(side="right", padx=2)
        DS.ghost_btn(toolbar, "Enable All", command=self._enable_all,
                     width=10).pack(side="right", padx=2)

        frame = tk.Frame(self.win, bg=BG_CARD)
        frame.pack(fill="both", expand=True, padx=10, pady=6)
        cols = ("Name", "Key", "Status", "Version", "Source", "Description")
        self._tree = ttk.Treeview(frame, columns=cols, show="headings", height=14)
        for c in cols:
            self._tree.heading(c, text=c)
        self._tree.column("Name", width=120)
        self._tree.column("Key", width=100)
        self._tree.column("Status", width=60)
        self._tree.column("Version", width=55)
        self._tree.column("Source", width=90)
        self._tree.column("Description", width=250)
        self._tree.pack(side="left", fill="both", expand=True)
        sb = DS.scrollbar(frame)
        sb.pack(side="right", fill="y")
        self._tree.config(yscrollcommand=sb.set)
        sb.config(command=self._tree.yview)

        DS.label(self.win, f"Active flows: {len(get_flow_map())}",
                 font=SMALL, fg=FG_DIM).pack(pady=(2, 6))
        self._populate()

    @staticmethod
    def _get_current_plugin_dir() -> str:
        from instareport.core.database import get_plugin_dir
        return get_plugin_dir()

    def _browse_plugin_dir(self) -> None:
        path = filedialog.askdirectory(title="Select Plugin Directory")
        if path:
            self._plugin_dir_var.set(path)

    def _set_plugin_dir(self) -> None:
        path = self._plugin_dir_var.get().strip()
        if not path:
            return
        from instareport.core.database import set_plugin_dir
        set_plugin_dir(path)
        self._refresh()
        log(f"Plugin directory set to {path}", "ok")

    def _backup_config(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Backup Config",
            defaultextension=".backup",
            filetypes=[("Backup files", "*.backup"), ("All files", "*.*")]
        )
        if not path:
            return
        from instareport.core.config import export_backup
        ok = export_backup(path)
        if ok:
            messagebox.showinfo("Backup", f"Config backed up to:\n{path}")
            log("Config backup created", "ok")
        else:
            messagebox.showerror("Backup Error", "Failed to create backup")

    def _restore_config(self) -> None:
        path = filedialog.askopenfilename(
            title="Restore Config",
            filetypes=[("Backup files", "*.backup"), ("All files", "*.*")]
        )
        if not path:
            return
        if not messagebox.askyesno("Restore Config",
                                    "This will overwrite current settings, accounts, "
                                    "and cooldowns. Continue?"):
            return
        from instareport.core.config import import_backup
        ok = import_backup(path)
        if ok:
            messagebox.showinfo("Restore", "Config restored successfully.\n"
                                           "Plugin directory will be re-scanned.")
            self._plugin_dir_var.set(self._get_current_plugin_dir())
            self._refresh()
            log("Config restored from backup", "ok")
        else:
            messagebox.showerror("Restore Error", "Failed to restore backup")

    def _populate(self) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)
        for p in sorted(get_all_plugins(), key=lambda x: x.display_name):
            status = "ON" if p.enabled else "OFF"
            source = getattr(p, "_source", "builtin")
            source_label = "[EXT]" if source != "builtin" and source else "[BUILTIN]"
            self._tree.insert("", "end", values=(
                p.display_name, p.platform_key, status, p.version,
                source_label, p.description
            ), tags=(p.platform_key,))

    def _refresh(self) -> None:
        discover_plugins()
        self._populate()
        count = len(get_all_plugins())
        active = len(get_flow_map())
        log(f"Plugins refreshed: {count} total, {active} active", "ok")

    def _get_selected_key(self) -> str | None:
        sel = self._tree.selection()
        if not sel:
            log("No plugin selected", "warn")
            return None
        return self._tree.item(sel[0], "values")[1]

    def _toggle_selected(self) -> None:
        key = self._get_selected_key()
        if not key:
            return
        from instareport.plugins.loader import get_plugin
        p = get_plugin(key)
        if p:
            set_plugin_enabled(key, not p.enabled)
            self._populate()
            log(f"Plugin '{p.display_name}' {'enabled' if p.enabled else 'disabled'}", "ok")

    def _enable_all(self) -> None:
        for p in get_all_plugins():
            set_plugin_enabled(p.platform_key, True)
        self._populate()
        log("All plugins enabled", "ok")

    def _disable_all(self) -> None:
        for p in get_all_plugins():
            set_plugin_enabled(p.platform_key, False)
        self._populate()
        log("All plugins disabled", "warn")

    def _import_plugin(self) -> None:
        path = filedialog.askopenfilename(
            title="Import Plugin",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        if not path:
            return
        result = import_plugin_file(path)
        if result:
            self._populate()
            log(f"Imported plugin: {result.display_name} ({result.platform_key})", "ok")
        else:
            log(f"No PlatformPlugin subclass found in {Path(path).name}", "err")
