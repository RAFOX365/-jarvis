import os
import sys
import shutil
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

VAULT = r"C:\Users\rafox\Documents\planodecultivo\thcLab\JARVIS"
__version__ = "1.2.0"


# -------------------------
# UTIL
# -------------------------
def _now_iso():
    return datetime.now().isoformat()


def _now_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _vault() -> Path:
    return Path(VAULT).resolve()


def _safe_within_vault(target: Path) -> bool:
    try:
        target.resolve().relative_to(_vault().resolve())
        return True
    except ValueError:
        return False


def _ok(path: str, data: Any = None) -> Dict[str, Any]:
    return {"ok": True, "path": path, "data": data}


def _fail(error: str) -> Dict[str, Any]:
    return {"ok": False, "error": error}


# -------------------------
# CORE
# -------------------------
def list_notes(folder: str = "Memory") -> Dict[str, Any]:
    folder_path = _vault() / folder
    if not folder_path.exists() or not folder_path.is_dir():
        return _ok("", data=[])
    notes = sorted(
        [p.name for p in folder_path.glob("*.md") if p.is_file()]
    )
    return _ok(str(folder_path), data=notes)


def read_note(folder: str, name: str) -> Dict[str, Any]:
    path = _vault() / folder / f"{name}.md"
    if not path.exists():
        return _fail("not_found")
    if not _safe_within_vault(path):
        return _fail("path_escape")
    try:
        content = path.read_text(encoding="utf-8")
        stats = {
            "size_bytes": len(content.encode("utf-8")),
            "lines": len(content.splitlines()),
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat()
        }
        return _ok(str(path), data={"content": content, "stats": stats})
    except UnicodeDecodeError:
        return _fail("encoding_error")
    except PermissionError:
        return _fail("permission_denied")


def write_note(folder: str, name: str, content: str) -> Dict[str, Any]:
    path = _vault() / folder / f"{name}.md"
    if not _safe_within_vault(path):
        return _fail("path_escape")

    old_hash = None
    if path.exists():
        try:
            old_hash = hashlib_existing(path)
        except Exception:
            pass

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    _log("WRITE_NOTE", {
        "file": str(path),
        "old_hash": old_hash,
        "new_hash": hashlib_existing(path)
    })

    return _ok(str(path))


def append_note(folder: str, name: str, content: str) -> Dict[str, Any]:
    path = _vault() / folder / f"{name}.md"
    if not _safe_within_vault(path):
        return _fail("path_escape")

    current = ""
    if path.exists():
        try:
            current = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return _fail("encoding_error")

    updated = current + "\n\n" + content
    path.write_text(updated, encoding="utf-8")

    _log("APPEND_NOTE", {"file": str(path)})
    return _ok(str(path))


def prepend_note(folder: str, name: str, content: str) -> Dict[str, Any]:
    path = _vault() / folder / f"{name}.md"
    if not _safe_within_vault(path):
        return _fail("path_escape")

    current = ""
    if path.exists():
        try:
            current = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return _fail("encoding_error")

    updated = content + "\n\n" + current
    path.write_text(updated, encoding="utf-8")

    _log("PREPEND_NOTE", {"file": str(path)})
    return _ok(str(path))


def patch_note(folder: str, name: str, old_text: str, new_text: str) -> Dict[str, Any]:
    path = _vault() / folder / f"{name}.md"
    if not _safe_within_vault(path):
        return _fail("path_escape")
    if not path.exists():
        return _fail("not_found")

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _fail("encoding_error")

    if old_text not in content:
        return _fail("pattern_not_found")

    updated = content.replace(old_text, new_text, 1)
    path.write_text(updated, encoding="utf-8")

    _log("PATCH_NOTE", {"file": str(path)})
    return _ok(str(path))


def delete_note(folder: str, name: str) -> Dict[str, Any]:
    path = _vault() / folder / f"{name}.md"
    if not path.exists():
        return _fail("not_found")
    if not _safe_within_vault(path):
        return _fail("path_escape")

    path.unlink()
    _log("DELETE_NOTE", {"file": str(path)})
    return _ok(str(path))


def copy_note(src_folder: str, src_name: str, dst_folder: str, dst_name: str) -> Dict[str, Any]:
    src = _vault() / src_folder / f"{src_name}.md"
    dst = _vault() / dst_folder / f"{dst_name}.md"
    if not src.exists():
        return _fail("src_not_found")
    if not _safe_within_vault(src) or not _safe_within_vault(dst):
        return _fail("path_escape")

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

    _log("COPY_NOTE", {"from": str(src), "to": str(dst)})
    return _ok(str(dst))


def move_note(src_folder: str, src_name: str, dst_folder: str, dst_name: str) -> Dict[str, Any]:
    src = _vault() / src_folder / f"{src_name}.md"
    dst = _vault() / dst_folder / f"{dst_name}.md"
    if not src.exists():
        return _fail("src_not_found")
    if not _safe_within_vault(src) or not _safe_within_vault(dst):
        return _fail("path_escape")

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))

    _log("MOVE_NOTE", {"from": str(src), "to": str(dst)})
    return _ok(str(dst))


def get_note_stats(folder: str, name: str) -> Dict[str, Any]:
    path = _vault() / folder / f"{name}.md"
    if not path.exists():
        return _fail("not_found")
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _fail("encoding_error")

    lines = content.splitlines()
    words = sum(len(line.split()) for line in lines)
    return _ok(str(path), data={
        "lines": len(lines),
        "words": words,
        "chars": len(content),
        "size_bytes": len(content.encode("utf-8")),
        "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    })


def find_notes_by_tag(tag: str) -> Dict[str, Any]:
    matches = []
    needle = f"#{tag}"
    for path in _vault().rglob("*.md"):
        if not _safe_within_vault(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if needle in text:
                matches.append(str(path))
        except Exception:
            pass

    _log("FIND_BY_TAG", {"tag": tag, "results": len(matches)})
    return _ok("", data=matches)


def extract_wikilinks(folder: str, name: str) -> Dict[str, Any]:
    path = _vault() / folder / f"{name}.md"
    if not path.exists():
        return _fail("not_found")
    text = path.read_text(encoding="utf-8")
    import re
    links = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text)
    return _ok(str(path), data=links)


def get_recent_notes(limit: int = 10) -> Dict[str, Any]:
    items = []
    for path in _vault().rglob("*.md"):
        if path.is_file():
            try:
                mtime = path.stat().st_mtime
                rel = str(path.relative_to(_vault()))
                items.append((mtime, rel))
            except Exception:
                pass
    items.sort(reverse=True)
    recent = [rel for _, rel in items[:limit]]
    return _ok("", data=recent)


def ensure_folder(folder: str) -> Dict[str, Any]:
    target = _vault() / folder
    target.mkdir(parents=True, exist_ok=True)
    return _ok(str(target))


def backup_note(folder: str, name: str) -> Dict[str, Any]:
    path = _vault() / folder / f"{name}.md"
    if not path.exists():
        return _fail("not_found")
    if not _safe_within_vault(path):
        return _fail("path_escape")

    stamp = _now_stamp()
    backup_dir = _vault() / "Snapshots" / "_manual"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{name}_{stamp}.md"

    shutil.copy2(path, backup_path)
    _log("BACKUP_NOTE", {"from": str(path), "to": str(backup_path)})
    return _ok(str(backup_path))


def info():
    return {
        "skill": "obsidian-fs",
        "version": __version__,
        "vault": str(VAULT),
        "actions": [
            "list_notes", "read_note", "write_note", "append_note",
            "prepend_note", "patch_note", "delete_note", "copy_note",
            "move_note", "get_note_stats", "find_notes_by_tag",
            "extract_wikilinks", "get_recent_notes", "ensure_folder",
            "backup_note", "info"
        ]
    }


# -------------------------
# LOG INTERNO (JSONL)
# -------------------------
def _log(event: str, data: Any):
    log_path = _vault() / "Logs" / "core.log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "time": _now_iso(),
        "event": event,
        "data": data,
        "version": __version__
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def hashlib_existing(path: Path) -> Optional[str]:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


# -------------------------
# BOOT
# -------------------------
if __name__ == "__main__":
    print("obsidian-fs standalone")
    print(info())
