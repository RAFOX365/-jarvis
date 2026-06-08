from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class KnowledgeGraphQueryEngine:
    def __init__(self, graph):
        self.graph = graph

    # -------------------------
    # EXISTING / BASE
    # -------------------------
    def get_node_context(self, node_id: str):
        node = self.graph.nodes.get(node_id)
        if node is None:
            return {"ok": False, "error": f"node not found: {node_id}"}
        neighbors = []
        for edge in self.graph.edges:
            if edge.get("source") == node_id or edge.get("target") == node_id:
                neighbors.append(edge)
        return {
            "ok": True,
            "node_id": node_id,
            "node": node,
            "neighbors": neighbors,
            "degree": len(neighbors),
        }

    def find_connection(self, from_id: str, to_id: str, max_depth: int = 4):
        visited = {from_id}
        queue = [(from_id, [from_id], 0)]
        while queue:
            current, path, depth = queue.pop(0)
            if current == to_id:
                return {
                    "ok": True,
                    "from": from_id,
                    "to": to_id,
                    "path": path,
                    "depth": depth,
                }
            if depth >= max_depth:
                continue
            for edge in self.graph.edges:
                nxt = None
                if edge.get("source") == current and edge.get("target") not in visited:
                    nxt = edge.get("target")
                elif edge.get("target") == current and edge.get("source") not in visited:
                    nxt = edge.get("source")
                if nxt is None:
                    continue
                visited.add(nxt)
                queue.append((nxt, path + [nxt], depth + 1))
        return {"ok": False, "from": from_id, "to": to_id, "reason": "no_path_found"}

    def search(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        terms = [t.lower() for t in re.split(r"\s+", query) if t]
        results: List[Dict[str, Any]] = []
        for node_id, node in self.graph.nodes.items():
            text = " ".join(
                str(node.get(k, ""))
                for k in ("title", "source", "tags", "type", "path", "hash", "preview")
            )
            text = (text + " " + str(node)).lower()
            score = max((text.count(t) for t in terms), default=0)
            if score > 0:
                results.append({"id": node_id, "node": node, "score": score})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:max_results]

    def nl_query_to_graph(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        matches = self.search(query, max_results=max_results)
        return {"ok": True, "query": query, "matches": matches}

    def export_subgraph_context(self, node_id: str, depth: int = 2) -> Dict[str, Any]:
        context = self.get_node_context(node_id)
        if not context.get("ok"):
            return context
        subgraph = {
            "nodes": {node_id: context["node"]},
            "edges": [],
            "explanations": [],
        }
        for edge in context["neighbors"]:
            nid = edge.get("target") if edge.get("source") == node_id else edge.get("source")
            subgraph["edges"].append(edge)
            neighbor = self.graph.nodes.get(nid)
            if neighbor:
                subgraph["nodes"][nid] = neighbor
            subgraph["explanations"].append({
                "from": node_id,
                "to": nid,
                "relation": edge.get("type"),
                "payload": edge.get("payload", {}),
            })
        subgraph["stats"] = {
            "nodes": len(subgraph["nodes"]),
            "edges": len(subgraph["edges"]),
        }
        return {"ok": True, "node_id": node_id, "subgraph": subgraph}

    # -------------------------
    # NEW / ADVANCED
    # -------------------------
    def related_nodes(self, node_id: str, rel_type: Optional[str] = None):
        node = self.graph.nodes.get(node_id)
        if node is None:
            return {"ok": False, "error": f"node not found: {node_id}"}
        related: List[Dict[str, Any]] = []
        for edge in self.graph.edges:
            if edge.get("source") == node_id:
                if rel_type and edge.get("type") != rel_type:
                    continue
                related.append({
                    "id": edge.get("target"),
                    "relation": edge.get("type"),
                    "edge": edge,
                    "node": self.graph.nodes.get(edge.get("target"), {}),
                })
            elif edge.get("target") == node_id:
                if rel_type and edge.get("type") != rel_type:
                    continue
                related.append({
                    "id": edge.get("source"),
                    "relation": edge.get("type"),
                    "edge": edge,
                    "node": self.graph.nodes.get(edge.get("source"), {}),
                })
        return {
            "ok": True,
            "node_id": node_id,
            "relation_filter": rel_type,
            "related": related,
            "count": len(related),
        }

    def knowledge_summary(self, node_ids: Optional[List[str]] = None, query: Optional[str] = None):
        items: List[Dict[str, Any]] = []
        ids = list(node_ids or [])
        if query:
            ids.extend([m["id"] for m in self.search(query)])
        seen: set = set()
        for nid in ids:
            if nid in seen:
                continue
            seen.add(nid)
            node = self.graph.nodes.get(nid)
            if not node:
                continue
            ctx = self.get_node_context(nid)
            items.append({
                "id": nid,
                "node": node,
                "degree": ctx.get("degree", 0),
                "relations": [
                    {
                        "id": (e.get("target") if e.get("source") == nid else e.get("source")),
                        "type": e.get("type"),
                    }
                    for e in ctx.get("neighbors", [])
                ],
            })
        return {
            "ok": True,
            "query": query,
            "count": len(items),
            "items": items,
            "stats": {
                "nodes": len(items),
                "edges": sum(len(i["relations"]) for i in items),
            },
        }

    def context_for_goal(self, goal: str, max_nodes: int = 6):
        matches = self.search(goal, max_results=max_nodes)
        nodes: Dict[str, Any] = {}
        edges: List[Dict[str, Any]] = []
        for m in matches:
            nid = m["id"]
            nodes[nid] = self.graph.nodes.get(nid, {})
            ctx = self.get_node_context(nid)
            for edge in ctx.get("neighbors", []):
                edges.append(edge)
                nid2 = edge.get("target") if edge.get("source") == nid else edge.get("source")
                if nid2 not in nodes:
                    nodes[nid2] = self.graph.nodes.get(nid2, {})
        return {
            "ok": True,
            "goal": goal,
            "context": {
                "matched": [m["id"] for m in matches],
                "nodes": nodes,
                "edges": edges,
                "scores": {m["id"]: m["score"] for m in matches},
                "stats": {
                    "nodes": len(nodes),
                    "edges": len(edges),
                },
            },
        }

    def resolve_entity(self, text: str):
        candidates = self.search(text)
        if not candidates:
            return {"ok": True, "matched": False, "candidates": [], "node_id": None}
        best = candidates[0]
        return {
            "ok": True,
            "matched": True,
            "candidates": candidates,
            "node_id": best["id"],
            "node": best["node"],
            "score": best["score"],
        }

    def recent_knowledge(self, limit: int = 10):
        items = []
        for nid, node in self.graph.nodes.items():
            created = node.get("created") or ""
            items.append((created, nid, node))
        items.sort(key=lambda x: x[0], reverse=True)
        return {
            "ok": True,
            "recent": [
                {"id": nid, "node": node, "created": created}
                for created, nid, node in items[:limit]
            ],
        }

    def get_subgraph(self, node_ids: List[str]):
        nodes: Dict[str, Any] = {}
        edges: List[Dict[str, Any]] = []
        for nid in node_ids:
            node = self.graph.nodes.get(nid)
            if not node:
                continue
            nodes[nid] = node
            for edge in self.graph.edges:
                if edge.get("source") == nid or edge.get("target") == nid:
                    edges.append(edge)
                    nid2 = edge.get("target") if edge.get("source") == nid else edge.get("source")
                    if nid2 not in nodes:
                        nodes[nid2] = self.graph.nodes.get(nid2, {})
        return {
            "ok": True,
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "nodes": len(nodes),
                "edges": len(edges),
            },
        }

    def build_context(self, node_id: str):
        ctx = self.get_node_context(node_id)
        if not ctx.get("ok"):
            return ctx
        node = ctx["node"]
        context = [node]
        edge_list = []
        for edge in ctx["neighbors"]:
            nxt = edge.get("target") if edge.get("source") == node_id else edge.get("source")
            edge_list.append(edge)
            neighbor = self.graph.nodes.get(nxt)
            if neighbor:
                context.append(neighbor)
        return {
            "ok": True,
            "query": node.get("title") or node_id,
            "context": context,
            "edges": edge_list,
            "stats": {
                "nodes": len(context),
                "edges": len(edge_list),
            },
        }

    # -------------------------
    # DISPATCH
    # -------------------------
    def execute(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        ACTIONS = {
            "search": self.search,
            "get_subgraph": self.get_subgraph,
            "find_path": self.find_connection,
            "build_context": self.build_context,
            "related_nodes": self.related_nodes,
            "recent_knowledge": self.recent_knowledge,
            "knowledge_summary": self.knowledge_summary,
            "resolve_entity": self.resolve_entity,
            "context_for_goal": self.context_for_goal,
        }
        fn = ACTIONS.get(action)
        if not fn:
            return {"ok": False, "error": f"unknown action: {action}"}
        try:
            return fn(**payload)
        except TypeError as exc:
            return {"ok": False, "error": str(exc)}
