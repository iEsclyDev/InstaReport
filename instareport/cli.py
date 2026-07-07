"""CLI headless mode — run reports from command line, JSON output, no Tkinter."""
import sys, json, os, asyncio, time
from datetime import datetime
from typing import Any

from instareport.utils.constants import VERSION, init_paths
from instareport.utils.logging import init_file_logger
from instareport.core.state import S, GLOBAL_STOP
from instareport.core.database import setup_persistence
from instareport.core.config import load_config, save_config
from instareport.plugins.loader import discover_plugins
from instareport.engine import mass_report_playwright


def _cli_log(msg: str, tag: str = "dim") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def run_cli(args: Any) -> int:
    init_paths()
    init_file_logger()
    setup_persistence()

    discover_plugins()

    output_format = getattr(args, "output_format", "json")

    if args.accounts:
        accts = []
        for line in args.accounts.split(","):
            if ":" in line:
                u, pw = line.split(":", 1)
                accts.append((u.strip(), pw.strip()))
        if accts:
            S.accounts = accts
            save_config()

    if args.target:
        S.target = args.target
    if args.platform:
        S.platform = args.platform
    if args.reason:
        S.reason = args.reason
    if args.workers:
        S.workers = args.workers
    if args.cooldown:
        S.cooldown_secs = args.cooldown
    S.headless = True

    if not S.accounts:
        print('{"error": "No accounts loaded. Use --accounts or load via config."}', file=sys.stderr)
        return 1
    if not S.target:
        print('{"error": "No target set. Use --target."}', file=sys.stderr)
        return 1

    targets = args.targets or [S.target]

    results: list[dict[str, Any]] = []
    for tgt in targets:
        if GLOBAL_STOP.is_set():
            break
        print(json.dumps({"event": "start", "target": tgt, "platform": S.platform, "reason": S.reason}))
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            successes = loop.run_until_complete(
                mass_report_playwright(tgt, S.platform, S.reason, _cli_log)
            )
            loop.close()
            result = {
                "target": tgt, "platform": S.platform, "reason": S.reason,
                "successes": successes, "total": len(S.accounts),
            }
            results.append(result)
            print(json.dumps({"event": "done", **result}))
        except Exception as e:
            print(json.dumps({"event": "error", "target": tgt, "error": str(e)}), file=sys.stderr)
            results.append({"target": tgt, "error": str(e)})

    summary = {
        "version": VERSION,
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "total_targets": len(results),
        "total_successes": sum(r.get("successes", 0) for r in results if "error" not in r),
    }
    if args.json or output_format == "json":
        print(json.dumps(summary, indent=2))
    elif output_format == "csv":
        import csv, io
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["target", "platform", "reason",
                                                  "successes", "total", "error"])
        writer.writeheader()
        for r in results:
            writer.writerow({k: r.get(k, "") for k in ["target", "platform", "reason",
                                                         "successes", "total", "error"]})
        print(buf.getvalue().strip())
    return 0 if all("error" not in r for r in results) else 1
