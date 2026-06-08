from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class _AutoBackup:
    def __init__(
        self,
        vault_path: str = ".",
        backup_root: str = "Backups",
        max_backups: int = 10,
    ) -> None:
        self.vault_path = Path(vault_path).resolve()
        self.backup_root = self.vault_path / backup_root
        self.max_backups = int(max_backups)
        self.backup_root.mkdir(parents=True, exist_ok=True)

    def info(self) -> Dict[str, Any]:
        return {
            "name": "auto-backup",
            "version": "1.0.0",
            "core_min_version": "3.3.0",
            "dependencies": [],
            "tags": ["backup", "ops", "vault"],
            "actions": [
                "create_snapshot",
                "list_backups",
                "restore_backup",
                "prune_old",
                "verify_latest",
            ],
        }

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    def _hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()[:12]

    def _execute(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        mapping: Dict[str, Any] = {
            "create_snapshot": self.create_snapshot,
            "list_backups": self.list_backups,
            "restore_backup": self.restore_backup,
            "prune_old": self.prune_old,
            "verify_latest": self.verify_latest,
        }
        fn = mapping.get(action)
        if not fn:
            return {"ok": False, "error": "unknown action: %s" % action}
        return fn(**payload)

    def create_snapshot(
        self,
        label: Optional[str] = None,
        compress: bool = True,
    ) -> Dict[str, Any]:
        stamp = self._timestamp()
        base_name = f"{stamp}"
        if label:
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
            base_name = f"{stamp}_{safe}"
        snapshot_dir = self.backup_root / base_name
        manifest_path = snapshot_dir / "manifest.json"

        included: List[str] = []
        manifest: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "label": label,
            "vault": str(self.vault_path),
            "files": included,
            "verification": {
                "sha256": "",
                "file_count": 0,
            },
        }

        snapshot_dir.mkdir(parents=True, exist_ok=True)
        copied = 0

        for src in sorted(self.vault_path.rglob("*")):
            if src.is_dir():
                continue
            rel = src.relative_to(self.vault_path)
            dst = snapshot_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if compress and dst.suffix not in {".zip", ".gz"}:
                shutil.copy2(src, dst)
            else:
                shutil.copy2(src, dst)
            included.append(str(rel))
            copied += 1

        archive_path: Optional[Path] = None
        if compress:
            archive_name = f"{base_name}.zip"
            archive_path = self.backup_root / archive_name
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for file_path in sorted(snapshot_dir.rglob("*")):
                    if file_path.is_file():
                        zf.write(file_path, file_path.relative_to(snapshot_dir))
            shutil.rmtree(snapshot_dir, ignore_errors=True)
            manifest["archive"] = str(archive_path)
            manifest["sha256"] = self._hash_file(archive_path)
            manifest["verification"]["sha256"] = manifest["sha256"]
            manifest["verification"]["file_count"] = copied
            meta_path = self.backup_root / f"{base_name}.meta.json"
            meta_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return {
                "ok": True,
                "backup": str(archive_path),
                "meta": str(meta_path),
                "file_count": copied,
            }

        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        manifest["sha256"] = self._hash_file(manifest_path)
        manifest["verification"]["sha256"] = manifest["sha256"]
        manifest["verification"]["file_count"] = copied
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {
            "ok": True,
            "backup": str(snapshot_dir),
            "manifest": str(manifest_path),
            "file_count": copied,
        }

    def list_backups(self) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        for path in sorted(self.backup_root.iterdir()):
            if path.is_dir() and path.name.count("-") >= 1:
                manifest = path / "manifest.json"
                if manifest.exists():
                    try:
                        data = json.loads(manifest.read_text(encoding="utf-8"))
                    except Exception:
                        data = {}
                    items.append(
                        {
                            "name": path.name,
                            "timestamp": data.get("timestamp"),
                            "label": data.get("label"),
                            "file_count": data.get("verification", {}).get("file_count"),
                            "sha256": data.get("verification", {}).get("sha256"),
                        }
                    )
                continue
            if path.is_file() and path.suffix == ".zip":
                meta = self.backup_root / f"{path.stem}.meta.json"
                meta_data: Dict[str, Any] = {}
                if meta.exists():
                    try:
                        meta_data = json.loads(meta.read_text(encoding="utf-8"))
                    except Exception:
                        meta_data = {}
                items.append(
                    {
                        "name": path.name,
                        "timestamp": meta_data.get("timestamp"),
                        "label": meta_data.get("label"),
                        "file_count": meta_data.get("verification", {}).get("file_count"),
                        "sha256": meta_data.get("verification", {}).get("sha256"),
                    }
                )
        return {"ok": True, "backups": items}

    def restore_backup(self, backup_name: str, target: Optional[str] = None) -> Dict[str, Any]:
        if target is None:
            restore_root = self.vault_path
        else:
            restore_root = Path(target).resolve()
        candidate = self.backup_root / backup_name
        if not candidate.exists():
            return {"ok": False, "error": "backup not found: %s" % backup_name}
        if candidate.is_dir():
            for src in sorted(candidate.rglob("*")):
                if src.is_file():
                    rel = src.relative_to(candidate)
                    dst = restore_root / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            return {"ok": True, "restored_to": str(restore_root)}
        if candidate.suffix == ".zip":
            with zipfile.ZipFile(candidate, "r") as zf:
                zf.extractall(restore_root)
            return {"ok": True, "restored_to": str(restore_root)}
        return {"ok": False, "error": "unsupported backup format: %s" % candidate.suffix}

    def prune_old(self, keep: int = 10) -> Dict[str, Any]:
        keep = max(1, int(keep))
        listing = self.list_backups()
        backups = listing.get("backups", []) or []
        removed: List[str] = []
        if len(backups) <= keep:
            return {"ok": True, "kept": len(backups), "removed": removed}
        excess = backups[keep:]
        for entry in excess:
            name = entry.get("name")
            if not name:
                continue
            path = self.backup_root / name
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
                removed.append(name)
            meta = self.backup_root / f"{Path(name).stem}.meta.json"
            if meta.exists():
                meta.unlink(missing_ok=True)
        return {"ok": True, "kept": keep, "removed": removed}

    def verify_latest(self) -> Dict[str, Any]:
        listing = self.list_backups()
        backups = listing.get("backups", []) or []
        if not backups:
            return {"ok": False, "error": "no backups found"}
        latest = backups[0]
        name = latest.get("name")
        if not name:
            return {"ok": False, "error": "invalid backup entry"}
        path = self.backup_root / name
        recorded = latest.get("sha256")
        if not recorded:
            return {"ok": True, "verified": False, "backup": latest}
        if path.is_file():
            actual = self._hash_file(path)
        else:
            files = [p for p in path.rglob("*") if p.is_file()]
            if not files:
                actual = ""
            else:
                actual = ""
                for file_path in files:
                    actual = hashlib.sha256((actual + self._hash_file(file_path)).encode("utf-8")).hexdigest()[:12]
        return {
            "ok": True,
            "verified": actual == recorded,
            "expected": recorded,
            "actual": actual,
            "backup": latest,
        }


_instance: Optional[_AutoBackup] = None


def _get_instance() -> _AutoBackup:
    global _instance
    if _instance is None:
        _instance = _AutoBackup(vault_path=str(Path(__file__).resolve().parent.parent))
    return _instance


def info() -> Dict[str, Any]:
    return _get_instance().info()


def execute(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return _get_instance()._execute(action, payload)


def create_snapshot(**payload: Any) -> Dict[str, Any]:
    return _get_instance()._execute("create_snapshot", payload)


def list_backups(**payload: Any) -> Dict[str, Any]:
    return _get_instance()._execute("list_backups", payload)


def restore_backup(**payload: Any) -> Dict[str, Any]:
    return _get_instance()._execute("restore_backup", payload)


def prune_old(**payload: Any) -> Dict[str, Any]:
    return _get_instance()._execute("prune_old", payload)


def verify_latest(**payload: Any) -> Dict[str, Any]:
    return _get_instance()._execute("verify_latest", payload)
