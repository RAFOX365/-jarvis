from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class KnowledgeMaintenance:
    def __init__(self, graph_path: Path, vault_path: Optional[Path] = None) -> None:
        self.graph_path = Path(graph_path)
        self.vault_path = Path(vault_path) if vault_path else None

    def info(self) -> Dict[str, Any]:
        return {
            "name": "knowledge-maintenance",
            "version": "1.0.0",
            "description": "Validação, estatística e reparo do KnowledgeGraph.",
            "core_min_version": "3.3.0",
            "dependencies": [],
            "tags": ["knowledge", "maintenance", "graph"],
            "actions": [
                "validate_graph",
                "graph_stats",
                "find_orphans",
                "repair_graph",
                "rebuild_index",
            ],
        }

    # -------------------------
    # LOAD / SAVE
    # -------------------------
    def _load_entries(self) -> List[Dict[str, Any]]:
        if not self.graph_path.exists():
            return []
        entries: List[Dict[str, Any]] = []
        for line in self.graph_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                entries.append({"__parse_error__": True, "raw": line})
        return entries

    # -------------------------
    # VALIDATE
    # -------------------------
    def validate_graph(self) -> Dict[str, Any]:
        entries = self._load_entries()
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        for idx, entry in enumerate(entries, start=1):
            etype = entry.get("type")
            if etype == "node":
                node_id = entry.get("id")
                if not node_id:
                    errors.append({"line": idx, "error": "node missing id"})
                    continue
                nodes[node_id] = entry.get("data", {})
            elif etype == "edge":
                edges.append(entry)
            elif "__parse_error__" in entry:
                errors.append({"line": idx, "error": "invalid_json", "raw": entry.get("raw", "")[:120]})
            else:
                errors.append({"line": idx, "error": f"unknown entry type: {etype}"})
        # cross-check edges
        orphan_edges = 0
        for edge in edges:
            src = edge.get("source")
            tgt = edge.get("target")
            if src not in nodes or tgt not in nodes:
                orphan_edges += 1
                errors.append({
                    "edge": edge,
                    "error": "edge references missing node",
                    "missing": ([src] if src not in nodes else []) + ([tgt] if tgt not in nodes else []),
                })
        return {
            "ok": len(errors) == 0,
            "lines": len(entries),
            "nodes": len(nodes),
            "edges": len(edges),
            "orphan_edges": orphan_edges,
            "errors": errors[:50],
        }

    # -------------------------
    # STATS
    # -------------------------
    def graph_stats(self) -> Dict[str, Any]:
        entries = self._load_entries()
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        for entry in entries:
            etype = entry.get("type")
            if etype == "node":
                node_id = entry.get("id")
                if node_id:
                    nodes[node_id] = entry.get("data", {})
            elif etype == "edge":
                edges.append(entry)

        tag_counts: Dict[str, int] = {}
        source_counts: Dict[str, int] = {}
        type_counts: Dict[str, int] = {}
        edge_type_counts: Dict[str, int] = {}
        for node in nodes.values():
            ntype = node.get("type") or "unknown"
            type_counts[ntype] = type_counts.get(ntype, 0) + 1
            for tag in node.get("tags", []) or []:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            source = node.get("source") or "unknown"
            source_counts[source] = source_counts.get(source, 0) + 1
        for edge in edges:
            edge_type = edge.get("type") or "unknown"
            edge_type_counts[edge_type] = edge_type_counts.get(edge_type, 0) + 1

        max_degree_node = None
        max_degree = -1
        degree_map: Dict[str, int] = {nid: 0 for nid in nodes}
        for edge in edges:
            src = edge.get("source")
            tgt = edge.get("target")
            if src in degree_map:
                degree_map[src] += 1
            if tgt in degree_map:
                degree_map[tgt] += 1
        for nid, deg in degree_map.items():
            if deg > max_degree:
                max_degree = deg
                max_degree_node = nid

        return {
            "ok": True,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "node_types": type_counts,
            "edge_types": edge_type_counts,
            "top_tags": sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_sources": sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            "max_degree": {
                "node_id": max_degree_node,
                "degree": max_degree,
            },
        }

    # -------------------------
    # FIND ORPHANS
    # -------------------------
    def find_orphans(self) -> Dict[str, Any]:
        entries = self._load_entries()
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        node_ids = set()
        for entry in entries:
            etype = entry.get("type")
            if etype == "node":
                node_id = entry.get("id")
                if node_id:
                    node_ids.add(node_id)
                    nodes[node_id] = entry.get("data", {})
            elif etype == "edge":
                edges.append(entry)
        orphan_nodes = sorted([nid for nid, node in nodes.items() if not any(
            e.get("source") == nid or e.get("target") == nid for e in edges
        )])
        orphan_edges = []
        for edge in edges:
            if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
                orphan_edges.append(edge)
        return {
            "ok": True,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "orphan_nodes": orphan_nodes,
            "orphan_nodes_count": len(orphan_nodes),
            "orphan_edges": orphan_edges,
            "orphan_edges_count": len(orphan_edges),
        }

    # -------------------------
    # REPAIR (safe)
    # -------------------------
    def repair_graph(self, dry_run: bool = True) -> Dict[str, Any]:
        entries = self._load_entries()
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        node_ids = set()
        for entry in entries:
            etype = entry.get("type")
            if etype == "node":
                node_id = entry.get("id")
                if node_id:
                    node_ids.add(node_id)
                    nodes[node_id] = entry.get("data", {})
            elif etype == "edge":
                edges.append(entry)
        repaired_nodes = 0
        repaired_edges = 0
        kept_nodes = []
        for nid, node in nodes.items():
            has_edge = any(e.get("source") == nid or e.get("target") == nid for e in edges)
            if not has_edge and node.get("type") != "root":
                if not dry_run:
                    # skip delete; instead mark as orphan and keep (safe default)
                    node["_orphan"] = True
                    repaired_nodes += 1
                kept_nodes.append({"type": "node", "id": nid, "data": node})
            else:
                kept_nodes.append({"type": "node", "id": nid, "data": node})
        kept_edges = []
        for edge in edges:
            if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
                repaired_edges += 1
                if not dry_run:
                    # skip delete; mark
                    edge["_invalid"] = True
                continue
            kept_edges.append(edge)
        report = {
            "ok": True,
            "dry_run": dry_run,
            "repaired_nodes": repaired_nodes,
            "repaired_edges": repaired_edges,
            "would_write_nodes": len(kept_nodes),
            "would_write_edges": len(kept_edges),
        }
        if not dry_run:
            lines = [json.dumps(obj, ensure_ascii=False) for obj in kept_nodes + kept_edges]
            self.graph_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            report["wrote"] = True
        else:
            report["wrote"] = False
        return report

    # -------------------------
    # REBUILD INDEX (recomputes from scratch)
    # -------------------------
    def rebuild_index(self) -> Dict[str, Any]:
        entries = self._load_entries()
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        seen_ids = set()
        for entry in entries:
            etype = entry.get("type")
            if etype == "node":
                node_id = entry.get("id")
                data = entry.get("data", {})
                if not node_id or "__parse_error__" in entry:
                    continue
                if node_id in seen_ids:
                    continue
                seen_ids.add(node_id)
                nodes[node_id] = data
            elif etype == "edge" and "__parse_error__" not in entry:
                edges.append(entry)
        rebuilt = []
        for nid, data in nodes.items():
            rebuilt.append(json.dumps({"type": "node", "id": nid, "data": data}, ensure_ascii=False))
        for edge in edges:
            rebuilt.append(json.dumps(edge, ensure_ascii=False))
        self.graph_path.write_text("\n".join(rebuilt) + "\n", encoding="utf-8")
        return {
            "ok": True,
            "wrote": True,
            "nodes": len(nodes),
            "edges": len(edges),
            "path": str(self.graph_path),
        }

    # -------------------------
    # DISPATCH
    # -------------------------
    def execute(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        mapping = {
            "validate_graph": self.validate_graph,
            "graph_stats": self.graph_stats,
            "find_orphans": self.find_orphans,
            "repair_graph": self.repair_graph,
            "rebuild_index": self.rebuild_index,
        }
        fn = mapping.get(action)
        if not fn:
            return {"ok": False, "error": f"unknown action: {action}"}
        try:
            return fn(**payload)
        except TypeError as exc:
            return {"ok": False, "error": str(exc)}
