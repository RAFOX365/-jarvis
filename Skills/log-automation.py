from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


class _LogAutomation:
    def __init__(self, vault_path: str, log_dir: str = "Logs") -> None:
        self.vault_path = Path(vault_path)
        self.log_dir = self.vault_path / log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._manifest_path = self.log_dir / "manifest.jsonl"
        self._ensure_manifest()

    def info(self) -> Dict[str, Any]:
        return {
            "name": "log-automation",
            "version": "1.0.0",
            "core_min_version": "3.3.0",
            "dependencies": [],
            "tags": ["logging", "audit", "ops"],
            "actions": [
                "rotate_logs",
                "export_audit_summary",
                "log_skill_execution",
                "manifest_stats",
            ],
        }

    def rotate_logs(self, keep_days: int = 30) -> Dict[str, Any]:
        cutoff = datetime.now() - timedelta(days=int(keep_days))
        if not self.log_dir.exists():
            return {"ok": True, "kept_days": keep_days, "removed": 0, "kept": []}
        kept: List[str] = []
        for path in sorted(self.log_dir.iterdir()):
            if not path.is_file():
                continue
            if path.suffix not in {".log", ".jsonl", ".md"}:
                continue
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError:
                continue
            if mtime >= cutoff:
                kept.append(str(path))
            else:
                path.unlink(missing_ok=True)

        return {"ok": True, "kept_days": keep_days, "removed": 0, "kept": kept}

    def export_audit_summary(self, output_file: str = "audit_summary.json") -> Dict[str, Any]:
        stats = {
            "log_dir": str(self.log_dir),
            "file_count": len(list(self.log_dir.glob("*.jsonl"))) if self.log_dir.exists() else 0,
            "manifest": str(self._manifest_path),
        }
        audit_data = {
            "timestamp": datetime.now().isoformat(),
            "vault_stats": stats,
            "snapshot_status": "active",
        }
        out_path = self.vault_path / output_file
        out_path.write_text(json.dumps(audit_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {"ok": True, "path": str(out_path), "data": audit_data}

    def log_skill_execution(self, skill_name: str, params: Dict[str, Any], result: Dict[str, Any], duration_ms: float) -> Dict[str, Any]:
        event_data = {
            "skill": skill_name,
            "params": params,
            "result": result,
            "duration_ms": duration_ms,
            "timestamp": datetime.now().isoformat(),
        }
        line = json.dumps(event_data, ensure_ascii=False) + "\n"
        manifest_path = self._manifest_path
        current = ""
        if manifest_path.exists():
            current = manifest_path.read_text(encoding="utf-8", errors="ignore")
        manifest: Dict[str, Any] = {}
        if current.strip():
            try:
                manifest = json.loads(current)
            except json.JSONDecodeError:
                manifest = {}
        manifest.setdefault("type", "manifest")
        manifest.setdefault("version", "1.0.0")
        manifest.setdefault("created", datetime.now().isoformat())
        manifest["updated"] = datetime.now().isoformat()
        manifest["entries"] = int(manifest.get("entries", 0)) + 1
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False) + "\n" + line, encoding="utf-8")
        return {"ok": True, "path": str(manifest_path)}

    def manifest_stats(self) -> Dict[str, Any]:
        if not self._manifest_path.exists():
            return {"ok": True, "path": str(self._manifest_path), "manifest": None}
        try:
            first = self._manifest_path.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
            manifest = json.loads(first)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "path": str(self._manifest_path)}
        return {"ok": True, "path": str(self._manifest_path), "manifest": manifest}

    def _execute(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        mapping: Dict[str, Any] = {
            "rotate_logs": self.rotate_logs,
            "export_audit_summary": self.export_audit_summary,
            "log_skill_execution": self.log_skill_execution,
            "manifest_stats": self.manifest_stats,
        }
        fn = mapping.get(action)
        if not fn:
            return {"ok": False, "error": "unknown action: %s" % action}
        return fn(**payload)

    def _ensure_manifest(self) -> None:
        if not self._manifest_path.exists():
            self._manifest_path.write_text(
                json.dumps(
                    {
                        "type": "manifest",
                        "version": "1.0.0",
                        "created": datetime.now().isoformat(),
                        "entries": 0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )


_instance: Optional[_LogAutomation] = None


def _get_instance() -> _LogAutomation:
    global _instance
    if _instance is None:
        _instance = _LogAutomation(vault_path=str(Path(__file__).resolve().parent.parent))
    return _instance


def info() -> Dict[str, Any]:
    return _get_instance().info()


def execute(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return _get_instance()._execute(action, payload)


def rotate_logs(**payload: Any) -> Dict[str, Any]:
    return _get_instance()._execute("rotate_logs", payload)


def export_audit_summary(**payload: Any) -> Dict[str, Any]:
    return _get_instance()._execute("export_audit_summary", payload)


def log_skill_execution(**payload: Any) -> Dict[str, Any]:
    return _get_instance()._execute("log_skill_execution", payload)


def manifest_stats(**payload: Any) -> Dict[str, Any]:
    return _get_instance()._execute("manifest_stats", payload)
