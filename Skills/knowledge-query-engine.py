from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


class KnowledgeGraphQueryEngine:
    def __init__(self, graph):
        self.graph = graph

    # -------------------------
    # GET NODE CONTEXT
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

    # -------------------------
    # FIND CONNECTION (A -> B)
    # -------------------------
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

    # -------------------------
    # SEARCH NODES (BASIC TEXT MATCH)
    # -------------------------
    def search(self, query: str, max_results: int = 20):
        terms = [t.lower() for t in re.split(r"\s+", query) if t]
        results = []
        for node_id, node in self.graph.nodes.items():
            text = " ".join(
                str(node.get(k, ""))
                for k in ("title", "source", "tags", "type", "path", "hash")
            )
            text = (text + " " + str(node)).lower()
            score = max((text.count(t) for t in terms), default=0)
            if score > 0:
                results.append({"id": node_id, "node": node, "score": score})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:max_results]

    # -------------------------
    # NL QUERY -> GRAPH QUERY
    # -------------------------
    def nl_query_to_graph(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        matches = self.search(query, max_results=max_results)
        return {"ok": True, "query": query, "matches": matches}

    # -------------------------
    # EXPORT SUBGRAPH CONTEXT
    # -------------------------
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
