# -*- coding: utf-8 -*-
"""GraphRAG retrieval over the existing knowledge-graph HTTP API.

The retriever is deliberately deterministic: it resolves a natural-language
question to a few anchor knowledge nodes, expands a bounded one-hop subgraph,
and returns compact evidence for the tutor LLM. It does not generate answers.
"""
import re
from typing import Any, Dict, Iterable, List, Optional

import config

MAX_ANCHORS = 3
DEFAULT_MAX_NODES = 8
MAX_FIELD_CHARS = 1200

_SPLIT_WORDS = re.compile(
    r"(?:和|与|跟|以及|及其|还有|、|，|,|；|;|之间|有什么|有何|"
    r"区别|差异|联系|关系|关联|为什么|为何|怎么|如何|哪些|什么|是否|"
    r"是不是|的前置|前置|前要|前先|需要|要学|先学|再学|学会|属于|基于|用到|是)"
)
_TRIM_PREFIXES = (
    "请问", "请", "帮我", "给我", "我想知道", "我想了解", "能不能", "可以",
    "讲讲", "讲一下", "解释一下", "解释", "介绍一下", "学习", "学",
)
_TRIM_SUFFIXES = (
    "吗", "呢", "啊", "吧", "的", "需要", "应该", "适合", "前置", "依赖",
    "知识体系", "适用场景",
)


def _unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "data" in value:
        return value["data"]
    return value


def _clip(value: Any, limit: int = MAX_FIELD_CHARS) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _dedupe(items: Iterable[str]) -> List[str]:
    result = []
    seen = set()
    for item in items:
        normalized = item.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def query_terms(query: str) -> List[str]:
    """Produce a few safe keyword searches from a Chinese natural-language query."""
    raw = re.sub(r"\s+", " ", (query or "").strip())
    if not raw:
        return []

    quoted = re.findall(r"[\"'“”‘’《》]([^\"'“”‘’《》]{2,30})[\"'“”‘’《》]", raw)
    chunks = _SPLIT_WORDS.split(raw)
    cleaned = []
    for chunk in chunks:
        value = chunk.strip(" \t\r\n。！？!?：:（）()[]【】")
        changed = True
        while changed and value:
            changed = False
            for prefix in _TRIM_PREFIXES:
                if value.startswith(prefix) and len(value) > len(prefix):
                    value = value[len(prefix):].strip()
                    changed = True
            for suffix in _TRIM_SUFFIXES:
                if value.endswith(suffix) and len(value) > len(suffix):
                    value = value[:-len(suffix)].strip()
                    changed = True
        if 2 <= len(value) <= 40:
            cleaned.append(value)

    # Try the original first because the backend also indexes teaching fields;
    # split terms recover named entities when the whole question is too strict.
    return _dedupe([raw, *quoted, *cleaned])[:6]


def _knowledge_hits(graph, terms: List[str], per_term: int) -> tuple:
    hits_by_term = []
    errors = []
    for term in terms:
        try:
            data = _unwrap(graph.search(
                keyword=term,
                node_types=["KnowledgeNode"],
                limit=per_term,
            )) or []
            hits = [h for h in data if isinstance(h, dict) and h.get("label") == "KnowledgeNode"]
            hits_by_term.append((term, hits))
        except Exception as exc:  # A partial keyword failure must not sink the whole retrieval.
            errors.append(f"search({term}): {exc}")
    return hits_by_term, errors


def _pick_anchors(hits_by_term: list) -> list:
    anchors = []
    seen = set()

    # Preserve the first distinct hit for each split term. This matters for
    # comparison questions such as "动态规划和分治有什么区别".
    for _term, hits in hits_by_term:
        if not hits:
            continue
        hit = hits[0]
        node_id = hit.get("id")
        if node_id and node_id not in seen:
            anchors.append(hit)
            seen.add(node_id)
        if len(anchors) >= MAX_ANCHORS:
            return anchors
    # Do not pad to MAX_ANCHORS with lower-ranked search hits. Related examples
    # belong in the graph expansion, not in the set of question entities.
    return anchors


def _mastery_state(node_id: str, mastery_by_id: Dict[str, float]) -> dict:
    if node_id not in mastery_by_id:
        return {"mastery": None, "learner_state": "unknown"}
    mastery = float(mastery_by_id[node_id])
    if mastery >= config.MASTERY_THRESHOLD:
        state = "mastered"
    elif mastery >= config.PRUNE_THRESHOLD:
        state = "likely_known"
    else:
        state = "weak"
    return {"mastery": round(mastery, 3), "learner_state": state}


def _node_from_properties(node_id: str, properties: dict, role: str,
                          mastery_by_id: Dict[str, float]) -> dict:
    node = {
        "id": node_id,
        "name": properties.get("name") or properties.get("title") or node_id,
        "roles": [role],
        **_mastery_state(node_id, mastery_by_id),
    }
    for key in ("overview", "elaboration", "applications", "learning_tips"):
        value = _clip(properties.get(key))
        if value:
            node[key] = value
    tags = properties.get("tags") or []
    if tags:
        node["tags"] = tags[:12] if isinstance(tags, list) else _clip(tags, 300)
    return node


def retrieve(query: str, graph, mastery_by_id: Optional[Dict[str, float]] = None,
             max_nodes: int = DEFAULT_MAX_NODES,
             topics: Optional[List[str]] = None) -> dict:
    """Return a compact, learner-aware graph evidence package for one question."""
    terms = _dedupe([*(topics or []), *query_terms(query)])[:6]
    max_nodes = max(3, min(12, int(max_nodes)))
    mastery_by_id = mastery_by_id or {}
    if not terms:
        return {"found": False, "query": query, "reason": "empty_query"}

    hits_by_term, errors = _knowledge_hits(graph, terms, per_term=max_nodes)
    anchors = _pick_anchors(hits_by_term)
    if not anchors:
        result = {"found": False, "query": query, "searched_terms": terms,
                  "reason": "no_knowledge_node"}
        if errors:
            result["partial_errors"] = errors
        return result

    nodes: Dict[str, dict] = {}
    edges = []
    edge_keys = set()

    def add_node(node_id: str, properties: dict, role: str):
        if not node_id:
            return
        if node_id in nodes:
            if role not in nodes[node_id]["roles"]:
                nodes[node_id]["roles"].append(role)
            return
        if len(nodes) < max_nodes:
            nodes[node_id] = _node_from_properties(
                node_id, properties or {}, role, mastery_by_id)

    def add_edge(source: str, target: str, rel_type: str, description: str = ""):
        if not source or not target or source not in nodes or target not in nodes:
            return
        key = (source, target, rel_type)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edge = {"source": source, "target": target, "type": rel_type}
        if description:
            edge["description"] = _clip(description, 400)
        edges.append(edge)

    anchor_order = [a.get("id") for a in anchors if a.get("id")]
    anchor_ids = set(anchor_order)
    for anchor in anchors:
        add_node(anchor.get("id"), anchor, "anchor")

    expansions = {anchor_id: [] for anchor_id in anchor_order}
    for anchor in anchors:
        anchor_id = anchor.get("id")
        anchor_name = anchor.get("name") or anchor_id
        related_nodes = []
        try:
            detail = _unwrap(graph.knowledge_point_detail(anchor_id)) or {}
            properties = detail.get("knowledge_point") if isinstance(detail, dict) else None
            if isinstance(properties, dict):
                # Replace the search projection with canonical detail while preserving roles.
                roles = nodes[anchor_id]["roles"]
                nodes[anchor_id] = _node_from_properties(
                    anchor_id, properties, roles[0], mastery_by_id)
                nodes[anchor_id]["roles"] = roles
                anchor_name = properties.get("name") or anchor_name
            related_nodes = detail.get("related_nodes") or [] if isinstance(detail, dict) else []
        except Exception as exc:
            errors.append(f"detail({anchor_id}): {exc}")

        try:
            dependency_data = _unwrap(graph.dependencies(anchor_name, depth=1)) or {}
            prerequisites = dependency_data.get("prerequisites") or []
            next_nodes = dependency_data.get("next") or []
        except Exception as exc:
            errors.append(f"dependencies({anchor_name}): {exc}")
            prerequisites, next_nodes = [], []

        for item in prerequisites:
            if not isinstance(item, dict):
                continue
            expansions[anchor_id].append({
                "id": item.get("id"), "properties": item, "role": "prerequisite",
                "source": anchor_id, "target": item.get("id"), "type": "PREREQUISITE",
            })
        for item in next_nodes:
            if not isinstance(item, dict):
                continue
            expansions[anchor_id].append({
                "id": item.get("id"), "properties": item, "role": "next",
                "source": item.get("id"), "target": anchor_id, "type": "PREREQUISITE",
            })

        for item in related_nodes:
            if not isinstance(item, dict):
                continue
            related_id = item.get("id") or item.get("node_id")
            rel_type = item.get("relation_type") or "RELATED_TO"
            role = "prerequisite" if rel_type == "PREREQUISITE" else "related"
            expansions[anchor_id].append({
                "id": related_id, "properties": item, "role": role,
                "source": anchor_id, "target": related_id, "type": rel_type,
                "description": item.get("description") or "",
            })

    # Spend the remaining node budget round-robin across anchors. Otherwise a
    # dense first anchor can crowd all evidence for the other side of a comparison.
    rounds = max((len(items) for items in expansions.values()), default=0)
    for index in range(rounds):
        for anchor_id in anchor_order:
            items = expansions[anchor_id]
            if index >= len(items):
                continue
            item = items[index]
            add_node(item["id"], item["properties"], item["role"])
            add_edge(item["source"], item["target"], item["type"],
                     item.get("description") or "")

    # Anchors must always survive a tight node budget. Cross-anchor edges are
    # retained when the backend explicitly exposes them.
    ordered_nodes = [nodes[node_id] for node_id in anchor_order if node_id in nodes]
    ordered_ids = {node["id"] for node in ordered_nodes}
    ordered_nodes.extend(node for node_id, node in nodes.items() if node_id not in ordered_ids)
    for index, node in enumerate(ordered_nodes, start=1):
        node["evidence_id"] = f"K{index}"

    result = {
        "found": True,
        "query": query,
        "searched_terms": terms,
        "retrieval_strategy": "keyword anchors + bounded one-hop graph expansion",
        "anchors": [{"id": a.get("id"), "name": a.get("name")} for a in anchors],
        "nodes": ordered_nodes,
        "edges": edges,
        "evidence_rule": "Answer only from these nodes and edges; state when the graph lacks evidence.",
    }
    if errors:
        result["partial_errors"] = errors
    return result
