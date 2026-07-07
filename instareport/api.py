"""REST API server for InstaReport — run with --api flag."""
import sys, json, asyncio, threading
from datetime import datetime
from typing import Any

from instareport.utils.constants import VERSION, init_paths
from instareport.utils.logging import init_file_logger, log
from instareport.core.state import S, GLOBAL_STOP
from instareport.core.database import setup_persistence, get_run_logs, get_run_logs_count
from instareport.core.config import load_config, save_config
from instareport.engine import mass_report_playwright

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
    _API_AVAILABLE = True
except ImportError:
    _API_AVAILABLE = False


app = FastAPI(title="InstaReport API", version=VERSION) if _API_AVAILABLE else None


class ReportRequest(BaseModel):
    target: str
    platform: str = "instagram"
    reason: str = "spam"
    accounts: list[str] = []
    workers: int = 0
    headless: bool = True


class ConfigUpdate(BaseModel):
    platform: str | None = None
    reason: str | None = None
    workers: int | None = None
    headless: bool | None = None
    stealth: bool | None = None
    cooldown_secs: int | None = None


if _API_AVAILABLE:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    running_reports: dict[str, Any] = {}

    @app.get("/")
    async def root() -> dict:
        return {"app": "InstaReport", "version": VERSION, "status": "running"}

    @app.get("/status")
    async def status() -> dict:
        return {
            "version": VERSION,
            "target": S.target,
            "platform": S.platform,
            "reason": S.reason,
            "accounts": len(S.accounts),
            "workers": S.workers,
            "headless": S.headless,
            "stealth": S.stealth,
            "scheduler_enabled": S.sched_enabled,
            "scheduler_time": S.sched_time,
            "active_reports": len(running_reports),
        }

    @app.get("/history")
    async def history(limit: int = 50, offset: int = 0) -> dict:
        rows = get_run_logs(limit=limit, offset=offset)
        total = get_run_logs_count()
        return {"total": total, "limit": limit, "offset": offset, "results": rows}

    @app.post("/report")
    async def start_report(req: ReportRequest) -> dict:
        if req.accounts:
            accts = []
            for a in req.accounts:
                if ":" in a:
                    u, p = a.split(":", 1)
                    accts.append((u, p))
            if accts:
                S.accounts = accts
        S.target = req.target
        S.platform = req.platform
        S.reason = req.reason
        if req.workers:
            S.workers = req.workers
        S.headless = req.headless
        S.stop_event.clear()
        GLOBAL_STOP.clear()

        report_id = datetime.now().strftime("%Y%m%d%H%M%S")
        running_reports[report_id] = {"status": "running", "target": req.target}

        async def _run() -> None:
            try:
                successes = await mass_report_playwright(
                    req.target, req.platform, req.reason,
                    lambda m, tag="dim": log(m, tag)
                )
                running_reports[report_id]["status"] = "done"
                running_reports[report_id]["successes"] = successes
            except Exception as e:
                running_reports[report_id]["status"] = "error"
                running_reports[report_id]["error"] = str(e)

        asyncio.create_task(_run())
        return {"report_id": report_id, "target": req.target, "status": "started"}

    @app.get("/report/{report_id}")
    async def report_status(report_id: str) -> dict:
        r = running_reports.get(report_id)
        if not r:
            raise HTTPException(status_code=404, detail="Report not found")
        return {"report_id": report_id, **r}

    @app.post("/config")
    async def update_config(cfg: ConfigUpdate) -> dict:
        if cfg.platform is not None:
            S.platform = cfg.platform
        if cfg.reason is not None:
            S.reason = cfg.reason
        if cfg.workers is not None:
            S.workers = cfg.workers
        if cfg.headless is not None:
            S.headless = cfg.headless
        if cfg.stealth is not None:
            S.stealth = cfg.stealth
        if cfg.cooldown_secs is not None:
            S.cooldown_secs = cfg.cooldown_secs
        save_config()
        return {"status": "updated"}

    @app.post("/stop")
    async def stop_all() -> dict:
        GLOBAL_STOP.set()
        S.stop_event.set()
        running_reports.clear()
        return {"status": "stopped"}


def run_api(host: str = "0.0.0.0", port: int = 8765) -> None:
    if not _API_AVAILABLE:
        print("FastAPI/uvicorn not installed. Run: pip install fastapi uvicorn")
        sys.exit(1)
    init_paths()
    init_file_logger()
    setup_persistence()
    load_config()
    log(f"[API] Starting on {host}:{port}", "ok")
    print(f"InstaReport API running at http://{host}:{port}")
    print(f"Docs at http://{host}:{port}/docs")
    uvicorn.run(app, host=host, port=port, log_level="info")
