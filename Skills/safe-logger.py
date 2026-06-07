import json
import os
import sys
import threading
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

VAULT = r"C:\Users\rafox\Documents\planodecultivo\thcLab\JARVIS"
__version__ = "2.0.0"


# -------------------------
# LOG LEVELS
# -------------------------
LOG_LEVELS = {
    "DEBUG": 10,
    "INFO": 20,
    "WARN": 30,
    "ERROR": 40
}


class SafeLogger:

    def __init__(
        self,
        path: Optional[Union[str, Path]] = None,
        vault_path: str = VAULT,
        max_size_mb: float = 5.0,
        max_backups: int = 5,
        min_level: str = "DEBUG",
        fsync_every_write: bool = False,
        encoding: str = "utf-8"
    ):
        if path is None:
            path = Path(vault_path) / "Logs" / "core.log.jsonl"
        self.path = Path(path).resolve()
        self.max_size_mb = max_size_mb
        self.max_backups = max_backups
        self.min_level = LOG_LEVELS.get(min_level.upper(), 20)
        self.fsync_every_write = fsync_every_write
        self.encoding = encoding
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_write_iso: Optional[str] = None

    # -------------------------
    # CONTEXT MANAGER
    # -------------------------
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    # -------------------------
    # CORE WRITE
    # -------------------------
    def write(self, event: str, data: Any, version: str = __version__, level: str = "INFO") -> Dict[str, Any]:
        level_upper = level.upper()
        if LOG_LEVELS.get(level_upper, 20) < self.min_level:
            return {"skipped": True, "reason": "below_min_level"}

        entry = {
            "time": datetime.now().isoformat(),
            "level": level_upper,
            "event": event,
            "version": version,
            "data": data
        }

        line = json.dumps(entry, ensure_ascii=False)

        with self.lock:
            self._rotate_if_needed()
            with open(self.path, "a", encoding=self.encoding) as f:
                f.write(line + "\n")
                if self.fsync_every_write:
                    f.flush()
                    os.fsync(f.fileno())

        self._last_write_iso = entry["time"]
        return entry

    # -------------------------
    # ROTATION + CLEANUP
    # -------------------------
    def _rotate_if_needed(self):
        if not self.path.exists():
            return
        try:
            size_mb = self.path.stat().st_size / (1024 * 1024)
        except OSError:
            return

        if size_mb >= self.max_size_mb:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = self.path.with_suffix(f".{stamp}.bak")
            try:
                self.path.rename(backup)
            except OSError:
                return
            self._cleanup_backups()
            # restart fresh file
            try:
                self.path.touch(exist_ok=True)
            except OSError:
                pass

    def _cleanup_backups(self):
        if self.max_backups <= 0:
            return
        pattern = re.compile(r"\.\d{8}_\d{6}\.bak$")
        backups = [
            p for p in self.path.parent.iterdir()
            if p.is_file() and pattern.search(p.name)
        ]
        if len(backups) <= self.max_backups:
            return
        backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[self.max_backups:]:
            try:
                old.unlink()
            except OSError:
                pass

    # -------------------------
    # TAIL / READ
    # -------------------------
    def tail(self, n: int = 20) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = []
        try:
            with open(self.path, "r", encoding=self.encoding, errors="replace") as f:
                all_lines = f.readlines()
                lines = all_lines[-n:]
        except OSError:
            return []
        result = []
        for line in lines:
            try:
                obj = json.loads(line.strip())
                if isinstance(obj, dict):
                    result.append(obj)
            except json.JSONDecodeError:
                continue
        return result

    def read_since(self, timestamp: str, limit: int = 200) -> List[Dict[str, Any]]:
        result = []
        if not self.path.exists():
            return result
        try:
            with open(self.path, "r", encoding=self.encoding, errors="replace") as f:
                for line in f:
                    try:
                        obj = json.loads(line.strip())
                        if isinstance(obj, dict) and obj.get("time", "") >= timestamp:
                            result.append(obj)
                            if len(result) >= limit:
                                break
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        return result

    def search(self, query: str, field: str = "event", limit: int = 100) -> List[Dict[str, Any]]:
        result = []
        q = query.lower()
        if not self.path.exists():
            return result
        try:
            with open(self.path, "r", encoding=self.encoding, errors="replace") as f:
                for line in f:
                    try:
                        obj = json.loads(line.strip())
                        if isinstance(obj, dict):
                            haystack = str(obj.get(field, "")).lower()
                            if q in haystack:
                                result.append(obj)
                                if len(result) >= limit:
                                    break
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        return result

    # -------------------------
    # STATS
    # -------------------------
    def get_stats(self) -> Dict[str, Any]:
        stats = {
            "path": str(self.path),
            "exists": self.path.exists(),
            "size_bytes": 0,
            "size_mb": 0.0,
            "lines": 0,
            "backups": 0,
            "last_write": self._last_write_iso
        }
        if not self.path.exists():
            return stats
        try:
            stats["size_bytes"] = self.path.stat().st_size
            stats["size_mb"] = round(stats["size_bytes"] / (1024 * 1024), 3)
            with open(self.path, "r", encoding=self.encoding, errors="replace") as f:
                stats["lines"] = sum(1 for _ in f)
        except OSError:
            pass

        pattern = re.compile(r"\.\d{8}_\d{6}\.bak$")
        try:
            backups = [
                p for p in self.path.parent.iterdir()
                if p.is_file() and pattern.search(p.name)
            ]
            stats["backups"] = len(backups)
        except OSError:
            pass

        return stats

    # -------------------------
    # CONVENIENCE: shutdown / flush
    # -------------------------
    def close(self):
        # No-op for compatibility; logs are append-only and flushed per write
        return True

    def info(self):
        return {
            "logger": "SafeLogger",
            "version": __version__,
            "path": str(self.path),
            "max_size_mb": self.max_size_mb,
            "max_backups": self.max_backups,
            "min_level": self.min_level,
            "fsync_every_write": self.fsync_every_write
        }


# -------------------------
# SHORTCUTS
# -------------------------
_default_path = Path(VAULT) / "Logs" / "core.log.jsonl"
_default_logger = SafeLogger(_default_path)


def write(event: str, data: Any, version: str = __version__, level: str = "INFO"):
    return _default_logger.write(event, data, version=version, level=level)


def tail(n: int = 20):
    return _default_logger.tail(n)


def search(query: str, field: str = "event", limit: int = 100):
    return _default_logger.search(query, field=field, limit=limit)


def stats():
    return _default_logger.get_stats()


# -------------------------
# BOOT
# -------------------------
if __name__ == "__main__":
    print("SafeLogger standalone")
    print(_default_logger.info())
    print("Stats:", _default_logger.get_stats())
