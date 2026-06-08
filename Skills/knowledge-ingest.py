from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class KnowledgeGraph:
    def __init__(self, graph_path: Path) -> None:
        self.graph_path = graph_path
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self.graph_path.exists():
            return
        for line in self.graph_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = entry.get("type")
            if etype == "node":
                node_id = entry.get("id")
                if node_id:
                    self.nodes[node_id] = entry.get("data", {})
            elif etype == "edge":
                self.edges.append(entry)

    def add_node(self, node_type: str, data: Dict[str, Any]) -> Optional[str]:
        # Prefer canonical hash from payload so callers can reference nodes consistently.
        node_id = str(data.get("hash") or "").strip()
        if not node_id:
            raw = json.dumps({"type": node_type, "data": data}, sort_keys=True, ensure_ascii=False)
            node_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        if node_id in self.nodes:
            return node_id
        self.nodes[node_id] = {"type": node_type, **data}
        self._append({"type": "node", "id": node_id, "data": self.nodes[node_id]})
        return node_id

    def add_edge(self, source: str, target: str, rel_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        edge = {
            "source": source,
            "target": target,
            "type": rel_type,
            "created": datetime.now().isoformat(),
        }
        if payload:
            edge["payload"] = payload
        self.edges.append(edge)
        self._append({"type": "edge", **edge})
        return {"ok": True, "edge": edge}

    def neighbors(self, node_id: str, rel_type: Optional[str] = None) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for edge in self.edges:
            if edge.get("source") == node_id or edge.get("target") == node_id:
                if rel_type and edge.get("type") != rel_type:
                    continue
                neighbor_id = edge.get("target") if edge.get("source") == node_id else edge.get("source")
                node = self.nodes.get(neighbor_id, {})
                out.append({"node_id": neighbor_id, "node": node, "edge": edge})
        return out

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        terms = [t.lower() for t in re.split(r"\s+", query) if t]
        if not terms:
            return []
        scored: List[Dict[str, Any]] = []
        for node_id, node in self.nodes.items():
            text = json.dumps(node, ensure_ascii=False).lower()
            score = sum(text.count(t) for t in terms)
            if score > 0:
                scored.append({"node_id": node_id, "node": node, "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:max_results]

    def _append(self, obj: Dict[str, Any]) -> None:
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        with self.graph_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def export(self) -> Dict[str, Any]:
        return {
            "nodes": self.nodes,
            "edges": self.edges,
        }


class KnowledgeIngest:
    def __init__(
        self,
        vault_path: str,
        memory: Optional[Any] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self.vault = Path(vault_path).resolve()
        self.memory = memory
        self.event_bus = event_bus
        self.base_path = self.vault / "Learnings"
        self.graph = KnowledgeGraph(self.base_path / "KnowledgeGraph" / "graph.jsonl")

    def info(self) -> Dict[str, object]:
        return {
            "name": "knowledge-ingest",
            "version": "1.0.0",
            "description": "Ingestão estruturada de conhecimento no Obsidian + EventGraph.",
            "actions": [
                "ingest_text",
                "ingest_url",
                "ingest_audio",
                "link_related",
                "search_knowledge",
                "graph_search",
                "graph_neighbors",
                "graph_export",
                "list_sources",
            ],
        }

    def list_sources(self) -> Dict[str, object]:
        items: List[Dict[str, str]] = []
        imports_root = self.vault / "Imports"
        if not imports_root.exists():
            return {"ok": True, "sources": items}
        for path in sorted(imports_root.rglob("*")):
            if path.is_file():
                items.append(
                    {
                        "source": str(path.relative_to(imports_root)),
                        "path": str(path),
                        "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                    }
                )
        return {"ok": True, "sources": items}

    def ingest_text(
        self,
        source: str,
        content: str,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        related: Optional[List[str]] = None,
    ) -> Dict[str, object]:
        if not source:
            return {"ok": False, "error": "source is required"}
        if not content:
            return {"ok": False, "error": "content is required"}
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
        title = title or source
        tags = tags or []
        related = related or []
        folder = self.base_path / "Insights"
        folder.mkdir(parents=True, exist_ok=True)
        file_path = folder / f"{self._slugify(title)} - {content_hash}.md"
        meta = {
            "title": title,
            "source": source,
            "hash": content_hash,
            "created": datetime.now().isoformat(),
            "tags": tags,
            "related": related,
            "status": "ingested",
        }
        file_path.write_text(self._render_note(meta, content), encoding="utf-8")
        node_id = meta["hash"]
        self.graph.add_node(
            node_type="knowledge",
            data={
                "title": title,
                "source": source,
                "hash": content_hash,
                "path": str(file_path),
                "tags": tags,
                "created": meta.get("created"),
                "preview": content[:500],
            },
        )
        if self.memory and hasattr(self.memory, "add_node"):
            try:
                self.memory.add_node("knowledge", meta)
            except Exception:
                pass
        if self.event_bus:
            try:
                self.event_bus.emit(
                    "KNOWLEDGE_INGESTED",
                    {
                        "source": source,
                        "node_id": node_id,
                        "hash": content_hash,
                        "path": str(file_path),
                    },
                )
            except Exception:
                pass
        return {"ok": True, "path": str(file_path), "node_id": node_id, "hash": content_hash}

    def ingest_url(
        self,
        url: str,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        content_override: Optional[str] = None,
    ) -> Dict[str, object]:
        if not url:
            return {"ok": False, "error": "url is required"}
        title = title or self._url_to_title(url)
        if content_override:
            return self.ingest_text(
                source=url,
                title=title,
                content=content_override,
                tags=tags or ["web", "research"],
            )
        return {
            "ok": False,
            "error": "content_override is required until browser extraction is implemented",
        }

    def ingest_audio(
        self,
        audio_path: str,
        transcription: str,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        related: Optional[List[str]] = None,
    ) -> Dict[str, object]:
        tags = tags or []
        if "audio" not in tags:
            tags.append("audio")
        if "transcription" not in tags:
            tags.append("transcription")
        return self.ingest_text(
            source=audio_path,
            title=title or Path(audio_path).stem,
            content=transcription,
            tags=tags,
            related=related,
        )

    def link_related(
        self,
        node_a_hash: Optional[str] = None,
        node_b_hash: Optional[str] = None,
        node_a: Optional[str] = None,
        node_b: Optional[str] = None,
        path_a: Optional[str] = None,
        path_b: Optional[str] = None,
    ) -> Dict[str, object]:
        a_id = node_a_hash or node_a or (path_a and self._path_to_node_id(path_a))
        b_id = node_b_hash or node_b or (path_b and self._path_to_node_id(path_b))
        if not a_id or not b_id:
            return {"ok": False, "error": "could not resolve both endpoints"}
        if self.memory and hasattr(self.memory, "add_edge"):
            self.memory.add_edge(a_id, b_id, "RELATED_TO")
        result = self.graph.add_edge(a_id, b_id, "RELATED_TO")
        if self.event_bus:
            self.event_bus.emit(
                "KNOWLEDGE_LINKED",
                {"from": a_id, "to": b_id, "edge": result},
            )
        return {"ok": True, "from": a_id, "to": b_id}

    def search_knowledge(self, query: str, max_results: int = 20) -> Dict[str, object]:
        if not query:
            return {"ok": False, "error": "query is required"}
        terms = [t.lower() for t in re.split(r"\s+", query) if t]
        results: List[Dict[str, Any]] = []
        for path in sorted(self.base_path.rglob("*.md")):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                continue
            score = sum(text.count(t) for t in terms)
            if score > 0:
                results.append(
                    {
                        "path": str(path),
                        "id": path.stem,
                        "score": score,
                        "preview": text[:300].replace("\n", " "),
                    }
                )
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return {"ok": True, "query": query, "results": results[:max_results]}

    def graph_search(self, query: str, max_results: int = 10) -> Dict[str, object]:
        if not query:
            return {"ok": False, "error": "query is required"}
        results = []
        for item in self.graph.search(query, max_results=max_results):
            results.append(
                {
                    "node_id": item["node_id"],
                    "node": item["node"],
                    "score": item.get("score", 0),
                }
            )
        return {"ok": True, "query": query, "results": results}

    def graph_neighbors(
        self,
        node_id: str,
        rel_type: Optional[str] = None,
        max_results: int = 20,
    ) -> Dict[str, object]:
        if not node_id:
            return {"ok": False, "error": "node_id is required"}
        neighbors = self.graph.neighbors(node_id, rel_type=rel_type)
        return {
            "ok": True,
            "node_id": node_id,
            "rel_type": rel_type,
            "neighbors": neighbors[:max_results],
        }

    def graph_export(self) -> Dict[str, object]:
        return {"ok": True, "graph": self.graph.export()}

    def _render_note(self, meta: Dict[str, Any], content: str) -> str:
        lines = ["---\n"]
        for key in ("title", "source", "hash", "created", "status", "type", "course"):
            value = meta.get(key)
            if value not in (None, "", []):
                if isinstance(value, str) and ("\n" in value or '"' in value or value.startswith("{") or value.startswith("[")):
                    lines.append(f"{key}:\n")
                    for part in value.splitlines():
                        lines.append(f"  {part}\n")
                else:
                    lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}\n")
        if meta.get("tags"):
            lines.append("tags:\n")
            for tag in meta["tags"]:
                lines.append(f"  - {tag}\n")
        if meta.get("related"):
            lines.append("related:\n")
            for rel in meta["related"]:
                lines.append(f"  - [[{rel}]]\n")
        lines.append("---\n")
        return "".join(lines) + "\n" + content.strip() + "\n"

    def _slugify(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r"[^a-z0-9]+", "-", text)
        text = re.sub(r"-{2,}", "-", text).strip("-")
        return text or hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]

    def _url_to_title(self, url: str) -> str:
        try:
            from urllib.parse import urlparse, unquote
            path = urlparse(url).path
            candidate = unquote(path.split("/")[-1])
            if candidate:
                return candidate.replace("-", " ").title()
        except Exception:
            pass
        return url

    def _path_to_node_id(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]

    def execute(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        mapping = {
            "ingest_text": self.ingest_text,
            "ingest_url": self.ingest_url,
            "ingest_audio": self.ingest_audio,
            "link_related": self.link_related,
            "search_knowledge": self.search_knowledge,
            "graph_search": self.graph_search,
            "graph_neighbors": self.graph_neighbors,
            "graph_export": self.graph_export,
            "list_sources": self.list_sources,
        }
        fn = mapping.get(action)
        if not fn:
            return {"ok": False, "error": f"unknown action: {action}"}
        try:
            return fn(**payload)
        except TypeError as exc:
            return {"ok": False, "error": str(exc)}
