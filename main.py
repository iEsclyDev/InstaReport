#!/usr/bin/env python3
"""InstaReport entry point — checks deps, monkey-patches asyncio, launches GUI or CLI."""
import sys, os, subprocess, importlib, argparse
from pathlib import Path
from typing import Any

# Static imports so Nuitka bundles these even if dep-check is skipped
import playwright, playwright_stealth, cryptography, requests  # noqa: F401

_REQUIRED = [
    "playwright", "playwright_stealth",
    "cryptography", "requests",
]

_MISSING = []
for pkg in _REQUIRED:
    try:
        importlib.import_module(pkg)
    except ImportError:
        _MISSING.append(pkg)

_parser = argparse.ArgumentParser(
    description="InstaReport — modular mass reporting tool",
    add_help=True,
)
_parser.add_argument("--cli", action="store_true", help="Run in CLI headless mode (no GUI)")
_parser.add_argument("--target", type=str, default="", help="Target username")
_parser.add_argument("--targets", type=str, nargs="*", default=[], help="Multiple target usernames")
_parser.add_argument("--platform", type=str, default="", help="Platform key (instagram, twitter, etc.)")
_parser.add_argument("--reason", type=str, default="", help="Report reason key (spam, harassment, etc.)")
_parser.add_argument("--accounts", type=str, default="", help="Comma-sep accounts user:pw,user:pw")
_parser.add_argument("--accounts-file", type=str, default="", help="Path to accounts file (user:pw per line)")
_parser.add_argument("--workers", type=int, default=0, help="Worker thread count")
_parser.add_argument("--cooldown", type=int, default=0, help="Cooldown seconds between reports")
_parser.add_argument("--json", action="store_true", help="Output results as JSON")
_parser.add_argument("--debug", action="store_true", help="Enable debug logging")
_parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
_parser.add_argument("--output-format", type=str, default="json",
                     choices=["json", "csv"], help="Output format (default: json)")
_parser.add_argument("--api", action="store_true", help="Run as REST API server")
_parser.add_argument("--api-host", type=str, default="0.0.0.0", help="API server host")
_parser.add_argument("--api-port", type=int, default=8765, help="API server port")
_parser.add_argument("--no-dep-check", action="store_true", help="Skip dependency check")
_parser.add_argument("--version", action="store_true", help="Print version and exit")
_args, _unknown = _parser.parse_known_args()

if _args.version:
    from instareport.utils.constants import VERSION
    print(f"InstaReport v{VERSION}")
    sys.exit(0)

if _args.no_dep_check:
    _MISSING.clear()

if _MISSING and not getattr(sys, "frozen", False):
    base_dir = Path(__file__).resolve().parent
    venv_dir = base_dir / ".venv"
    if sys.platform == "win32":
        py = venv_dir / "Scripts" / "python.exe"
    else:
        py = venv_dir / "bin" / "python"
    if not py.exists():
        import tkinter.messagebox as mb
        ans = mb.askyesno(
            "InstaReport Setup",
            "First run detected.\n\n"
            "Create isolated environment (.venv) and install dependencies?\n"
            "This won't affect your system Python."
        )
        if not ans:
            sys.exit(0)
        try:
            subprocess.check_call(
                [sys.executable, "-m", "venv", str(venv_dir)],
                creationflags=0x08000000 if sys.platform == "win32" else 0,
            )
            subprocess.check_call(
                [str(py), "-m", "pip", "install", "--upgrade", "pip"],
                creationflags=0x08000000 if sys.platform == "win32" else 0,
            )
            subprocess.check_call(
                [str(py), "-m", "pip", "install", *_REQUIRED],
                creationflags=0x08000000 if sys.platform == "win32" else 0,
            )
            subprocess.check_call(
                [str(py), "-m", "playwright", "install", "chromium"],
                creationflags=0x08000000 if sys.platform == "win32" else 0,
            )
        except Exception as e:
            mb.showerror("Setup Error", str(e))
            sys.exit(1)
    os.execv(str(py), [str(py), __file__] + sys.argv[1:])

if _args.api:
    if _MISSING:
        print(f"Missing dependencies: {', '.join(_MISSING)}", file=sys.stderr)
        sys.exit(1)
    if sys.platform == "win32" and sys.version_info >= (3, 8):
        try:
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
    from instareport.api import run_api
    sys.exit(run_api(host=_args.api_host, port=_args.api_port))

if _args.cli:
    if _MISSING:
        print(f"Missing dependencies: {', '.join(_MISSING)}", file=sys.stderr)
        print("Run without --cli to auto-install, or install manually.", file=sys.stderr)
        sys.exit(1)
    if _args.accounts_file:
        acct_lines = []
        try:
            with open(_args.accounts_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and ":" in line and not line.startswith("#"):
                        acct_lines.append(line)
        except Exception as e:
            print(f"Error reading accounts file: {e}", file=sys.stderr)
            sys.exit(1)
        _args.accounts = ",".join(acct_lines) if acct_lines else _args.accounts
    if sys.platform == "win32" and sys.version_info >= (3, 8):
        try:
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
    from instareport.cli import run_cli
    sys.exit(run_cli(_args))

if sys.platform == "win32" and sys.version_info >= (3, 8):
    try:
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

from instareport.app import App

if __name__ == "__main__":
    App().mainloop()
