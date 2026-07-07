import logging as _logging
from logging.handlers import RotatingFileHandler as _RFH

from instareport.utils.constants import DEBUG

_file_logger = _logging.getLogger("instareport")
_file_logger.setLevel(_logging.DEBUG)

def init_file_logger():
    if _file_logger.handlers:
        return
    try:
        _fh = _RFH("app.log", maxBytes=2*1024*1024, backupCount=3, encoding="utf-8")
        _fh.setFormatter(_logging.Formatter(
            "%(asctime)s %(levelname)-5s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"))
        _file_logger.addHandler(_fh)
    except Exception:
        pass

def flog(msg: str, level: str = "info"):
    _lvl_map = {"warn": "warning", "err": "error", "ok": "info",
                "sys": "info", "proxy": "info", "dim": "debug"}
    lvl = _lvl_map.get(level, level)
    getattr(_file_logger, lvl, _file_logger.info)(msg)

def log(msg, tag="dim"):
    from instareport.core.state import S
    if S.log_cb:
        S.log_cb(msg, tag)
    flog(msg, tag)

def dlog(msg):
    init_file_logger()
    if DEBUG:
        log(f"[DBG] {msg}", "dim")
