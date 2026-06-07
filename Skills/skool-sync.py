from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class SkoolSync:
    def __init__(self, exports_root: str | None = None) -> None:
        self.exports_root = Path(exports_root or Path(__file__).resolve().parent.parent / "Imports" / "Skool-classroom")

    def info(self) -> Dict[str, object]:
        return {
            "name": "skool-sync",
            "version": "0.1.0",
            "description": "Convert Skool classroom exports into Obsidian learning notes.",
            "actions": ["ingest_export", "list_sources"],
        }

    def list_sources(self) -> List[Dict[str, str]]:
        items: List[Dict[str, str]] = []
        if not self.exports_root.exists():
            return items
        for path in sorted(self.exports_root.glob("*.json")):
            items.append({"source": path.name, "path": str(path)})
        return items

    def ingest_export(self, source_path: str) -> Dict[str, object]:
        path = Path(source_path)
        if not path.exists():
            return {"ok": False, "error": f"Source not found: {path}"}
        payload = json.loads(path.read_text(encoding="utf-8"))
        course = payload.get("course", Path(path.stem).name)
        lesson_id = payload.get("lesson_id", hashlib.sha1(path.name.encode("utf-8")).hexdigest()[:10])
        lesson_title = payload.get("title", path.stem)
        body = payload.get("markdown") or payload.get("content") or ""
        note = self._build_note(course=course, lesson_id=lesson_id, title=lesson_title, body=body, source=path.name)
        return {"ok": True, "note_path": str(note), "source": path.name}

    def _build_note(self, course: str, lesson_id: str, title: str, body: str, source: str) -> Path:
        vault = self.exports_root.parent.parent
        learnings = vault / "Learnings" / "Skool"
        learnings.mkdir(parents=True, exist_ok=True)
        filename = f"{lesson_id} - {title}.md"
        target = learnings / filename
        today = datetime.now().strftime("%Y-%m-%d")
        content = (
            f"---\n"
            f"course: \"{course}\"\n"
            f"lesson_id: \"{lesson_id}\"\n"
            f"learned: \"{today}\"\n"
            f"source: \"{source}\"\n"
            f"status: ingested\n"
            f"tags:\n"
            f"  - learnings/skool\n"
            f"  - ai-business\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"{body}\n\n"
            f"---\n"
            f"_Imported from {source}_\n"
        )
        target.write_text(content, encoding="utf-8")
        return target
