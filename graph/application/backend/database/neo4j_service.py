"""Asynchronous Neo4j data-access service for the FastAPI application."""

import asyncio
import copy
from time import monotonic, perf_counter
from typing import Any, Dict, List, Optional

from loguru import logger
from neo4j import AsyncGraphDatabase, READ_ACCESS, WRITE_ACCESS, unit_of_work
from neo4j.exceptions import ServiceUnavailable, SessionExpired

from config import settings
from database.cypher_security import build_fulltext_query, validate_limit, validate_node_labels
from database.neo4j_exceptions import (
    Neo4jConnectionError,
    Neo4jQueryError,
    Neo4jQueryTimeoutError,
)
from observability import runtime_metrics


SEARCH_TERM_ALIASES = {
    "折半查找": "二分查找",
}


class Neo4jService:
    """Async data-access layer used only by the web application."""

    @staticmethod
    def _node_display_name(node_type: str, properties: Optional[Dict[str, Any]]) -> str:
        """Return the user-facing name for a graph node.

        Difficulty nodes are keyed by ``level`` rather than ``name`` in the
        imported graph data, so falling back directly to the Neo4j label would
        collapse all four levels into the same displayed text.
        """
        props = properties or {}
        if node_type == "Difficulty":
            value = props.get("level") or props.get("name") or props.get("title")
        else:
            value = props.get("name") or props.get("title")
        return str(value or node_type)

    def __init__(self) -> None:
        self.uri = settings.NEO4J_URI
        self.user = settings.NEO4J_USER
        self.password = settings.NEO4J_PASSWORD.get_secret_value()
        self.database = settings.NEO4J_DATABASE
        self.query_timeout = settings.NEO4J_QUERY_TIMEOUT_SECONDS
        self.fetch_size = settings.NEO4J_FETCH_SIZE
        self.driver = None
        self._connected = False
        self._statistics_cache: Optional[Dict[str, Any]] = None
        self._statistics_cache_expires_at = 0.0
        self._statistics_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self.driver is not None and self._connected

    async def connect(self) -> None:
        """Create the driver and verify connectivity.

        Connection failures are explicit so callers cannot confuse an
        unavailable database with a valid query that returned no rows.
        """
        if self.is_connected:
            return

        if self.driver is not None:
            try:
                await self.driver.verify_connectivity()
            except Exception:
                await self.close()
            else:
                self._connected = True
                return

        driver = None
        try:
            driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                max_connection_pool_size=settings.NEO4J_MAX_CONNECTION_POOL_SIZE,
                connection_timeout=settings.NEO4J_CONNECTION_TIMEOUT_SECONDS,
                connection_acquisition_timeout=(
                    settings.NEO4J_CONNECTION_ACQUISITION_TIMEOUT_SECONDS
                ),
                max_connection_lifetime=(
                    settings.NEO4J_MAX_CONNECTION_LIFETIME_SECONDS
                ),
                max_transaction_retry_time=(
                    settings.NEO4J_MAX_TRANSACTION_RETRY_TIME_SECONDS
                ),
                keep_alive=True,
            )
            await driver.verify_connectivity()
        except Exception as exc:
            if driver is not None:
                await driver.close()
            self.driver = None
            self._connected = False
            logger.error("Neo4j connectivity check failed: {}", type(exc).__name__)
            raise Neo4jConnectionError("无法连接 Neo4j 数据库") from exc

        self.driver = driver
        self._connected = True
        logger.info("已连接 Neo4j 数据库: {} / {}", self.uri, self.database)

    async def close(self) -> None:
        """Close the pool and prevent new sessions from being created."""
        driver = self.driver
        self.driver = None
        self._connected = False
        self.invalidate_statistics_cache()
        if driver is not None:
            await driver.close()
            logger.info("Neo4j 连接池已关闭")

    async def ping(self) -> bool:
        """Actively verify the driver can still reach Neo4j (for readiness probes)."""
        if self.driver is None:
            return False
        try:
            await self.driver.verify_connectivity()
        except Exception:
            self._connected = False
            return False
        self._connected = True
        return True

    def _require_driver(self):
        if self.driver is None:
            raise Neo4jConnectionError("Neo4j 数据库未连接")
        return self.driver

    @staticmethod
    def _is_timeout(exc: Exception) -> bool:
        code = str(getattr(exc, "code", ""))
        name = type(exc).__name__
        return (
            isinstance(exc, (TimeoutError, asyncio.TimeoutError))
            or "Timeout" in name
            or "TimedOut" in code
            or "Timeout" in code
        )

    async def _execute(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]],
        access_mode: str,
        timeout: Optional[float],
    ) -> List[Dict[str, Any]]:
        driver = self._require_driver()
        query_timeout = self.query_timeout if timeout is None else timeout
        if query_timeout <= 0:
            raise ValueError("query timeout 必须大于 0")

        async def run_query(transaction):
            result = await transaction.run(
                query,
                parameters or {},
            )
            return await result.data()

        transaction_work = unit_of_work(timeout=query_timeout)(run_query)

        started = perf_counter()
        failed = True
        try:
            async with driver.session(
                database=self.database,
                default_access_mode=access_mode,
                fetch_size=self.fetch_size,
            ) as session:
                if access_mode == READ_ACCESS:
                    records = await session.execute_read(transaction_work)
                else:
                    records = await session.execute_write(transaction_work)
            self._connected = True
            failed = False
            return records
        except Exception as exc:
            if self._is_timeout(exc):
                logger.error("Neo4j query timed out: {}", type(exc).__name__)
                raise Neo4jQueryTimeoutError("Neo4j 查询超时") from exc
            if isinstance(exc, (ServiceUnavailable, SessionExpired)):
                self._connected = False
                logger.error("Neo4j connection lost: {}", type(exc).__name__)
                raise Neo4jConnectionError("Neo4j 数据库不可用") from exc
            logger.error("Neo4j query failed: {}", type(exc).__name__)
            raise Neo4jQueryError("Neo4j 查询执行失败") from exc
        finally:
            duration_ms = (perf_counter() - started) * 1000
            slow = duration_ms >= settings.SLOW_QUERY_THRESHOLD_MS
            runtime_metrics.record_query(
                str(access_mode),
                duration_ms,
                failed=failed,
                slow=slow,
            )
            if slow:
                logger.warning(
                    "Slow Neo4j query: mode={} duration_ms={:.3f} threshold_ms={:.3f}",
                    str(access_mode).lower(),
                    duration_ms,
                    settings.SLOW_QUERY_THRESHOLD_MS,
                )

    async def execute_read(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a read transaction and return all records as dictionaries."""
        return await self._execute(query, parameters, READ_ACCESS, timeout)

    async def execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a write transaction and return any records it produces."""
        records = await self._execute(query, parameters, WRITE_ACCESS, timeout)
        self.invalidate_statistics_cache()
        return records

    async def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Compatibility alias for existing read-only API queries."""
        return await self.execute_read(query, parameters, timeout=timeout)

    def invalidate_statistics_cache(self) -> None:
        self._statistics_cache = None
        self._statistics_cache_expires_at = 0.0

    async def get_statistics(self, *, force_refresh: bool = False) -> Dict[str, Any]:
        """Return graph metadata using one query and a short in-process cache."""
        now = monotonic()
        if (
            not force_refresh
            and self._statistics_cache is not None
            and now < self._statistics_cache_expires_at
        ):
            return copy.deepcopy(self._statistics_cache)

        async with self._statistics_lock:
            now = monotonic()
            if (
                not force_refresh
                and self._statistics_cache is not None
                and now < self._statistics_cache_expires_at
            ):
                return copy.deepcopy(self._statistics_cache)

            query = """
            CALL {
                MATCH (n)
                WITH labels(n)[0] AS label, count(*) AS count
                ORDER BY label
                RETURN collect({label: label, count: count}) AS node_counts,
                       coalesce(sum(count), 0) AS total_nodes
            }
            CALL {
                MATCH ()-[r]->()
                WITH type(r) AS rel_type, count(*) AS count
                ORDER BY rel_type
                RETURN collect({type: rel_type, count: count}) AS rel_counts,
                       coalesce(sum(count), 0) AS total_relationships
            }
            RETURN node_counts, total_nodes, rel_counts, total_relationships
            """
            rows = await self.execute_read(query)
            row = rows[0] if rows else {
                "node_counts": [],
                "total_nodes": 0,
                "rel_counts": [],
                "total_relationships": 0,
            }
            node_counts = row["node_counts"]
            rel_counts = row["rel_counts"]
            statistics = {
                "nodes": {item["label"]: item["count"] for item in node_counts},
                "total_nodes": row["total_nodes"],
                "relationships": {
                    item["type"]: item["count"] for item in rel_counts
                },
                "total_relationships": row["total_relationships"],
                "labels": [item["label"] for item in node_counts],
                "relationship_types": [item["type"] for item in rel_counts],
            }
            self._statistics_cache = statistics
            self._statistics_cache_expires_at = (
                monotonic() + settings.GRAPH_STATISTICS_CACHE_TTL_SECONDS
            )
            return copy.deepcopy(statistics)

    @staticmethod
    def _normalize_search_keyword(keyword: str) -> str:
        normalized = keyword.strip()
        return SEARCH_TERM_ALIASES.get(normalized, normalized)

    @staticmethod
    def _fulltext_query(keyword: str) -> str:
        """Build a Lucene query without exposing operators from user input.

        Delegates to the shared helper also used by the question keyword
        search (B8) so both go through identical escaping rules.
        """
        return build_fulltext_query(keyword)

    async def _contains_search(
        self,
        keyword: str,
        safe_node_types: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        type_predicate = (
            "any(label IN labels(n) WHERE label IN $node_types)"
            if safe_node_types
            else "(n:KnowledgeNode OR n:Chapter OR n:Question)"
        )
        query = f"""
        MATCH (n)
        WHERE {type_predicate}
          AND (
            n.name CONTAINS $keyword
            OR n.title CONTAINS $keyword
            OR n.overview CONTAINS $keyword
            OR n.description CONTAINS $keyword
            OR n.category1 CONTAINS $keyword
            OR n.category2 CONTAINS $keyword
            OR n.section CONTAINS $keyword
          )
        RETURN coalesce(n.id, n.node_id, elementId(n)) as id,
               labels(n)[0] as label,
               properties(n) as properties,
               0.0 AS score
        LIMIT $limit
        """
        return await self.execute_read(
            query,
            {"keyword": keyword, "limit": limit, "node_types": safe_node_types},
        )

    async def search_nodes(
        self,
        keyword: str,
        node_types: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        keyword = self._normalize_search_keyword(keyword)
        if not keyword:
            raise ValueError("搜索关键词不能为空")
        limit = validate_limit(limit, maximum=200)
        safe_node_types = validate_node_labels(node_types)
        type_predicate = (
            "any(label IN labels(node) WHERE label IN $node_types)"
            if safe_node_types
            else "(node:KnowledgeNode OR node:Chapter OR node:Question)"
        )
        query = f"""
        CALL db.index.fulltext.queryNodes($index_name, $fulltext_query)
        YIELD node, score
        WHERE {type_predicate}
        RETURN coalesce(node.id, node.node_id, elementId(node)) as id,
               labels(node)[0] as label,
               properties(node) as properties,
               score
        ORDER BY score DESC, coalesce(node.name, node.title, '')
        LIMIT $limit
        """
        results = await self.execute_read(
            query,
            {
                "index_name": settings.NEO4J_FULLTEXT_INDEX_NAME,
                "fulltext_query": self._fulltext_query(keyword),
                "limit": limit,
                "node_types": safe_node_types,
            },
        )
        if not results:
            # The CJK analyzer does not index every one-character token.  Keep
            # the previous substring behavior only for this no-hit edge case.
            results = await self._contains_search(keyword, safe_node_types, limit)
        nodes = []
        for result in results:
            node = dict(result["properties"])
            node["id"] = result["id"]
            node["label"] = result["label"]
            node["search_score"] = result.get("score", 0.0)
            nodes.append(node)
        return nodes

    async def search_question_ids_by_keyword(
        self,
        keyword: str,
        limit: int = 2000,
    ) -> List[str]:
        """Resolve keyword to matching Question ids via the CJK fulltext index (B8).

        Used to filter the question list without a full-table CONTAINS scan.
        Falls back to CONTAINS only when the index has no hits (e.g. very
        short or purely numeric tokens the analyzer does not cover).
        """
        keyword = self._normalize_search_keyword(keyword)
        if not keyword:
            return []
        limit = validate_limit(limit, maximum=2000)
        query = """
        CALL db.index.fulltext.queryNodes($index_name, $fulltext_query)
        YIELD node, score
        WHERE node:Question AND (
            toLower(coalesce(node.id, '')) CONTAINS $keyword_folded OR
            toLower(coalesce(node.name, '')) CONTAINS $keyword_folded OR
            toLower(coalesce(node.description, '')) CONTAINS $keyword_folded
        )
        RETURN node.id AS id, score
        ORDER BY score DESC
        LIMIT $limit
        """
        rows = await self.execute_read(
            query,
            {
                "index_name": settings.NEO4J_FULLTEXT_INDEX_NAME,
                "fulltext_query": self._fulltext_query(keyword),
                "keyword_folded": keyword.casefold(),
                "limit": limit,
            },
        )
        if not rows:
            rows = await self.execute_read(
                """
                MATCH (q:Question)
                WHERE toLower(coalesce(q.id, '')) CONTAINS $keyword_folded
                   OR toLower(coalesce(q.name, '')) CONTAINS $keyword_folded
                   OR toLower(coalesce(q.description, '')) CONTAINS $keyword_folded
                RETURN q.id AS id
                LIMIT $limit
                """,
                {"keyword_folded": keyword.casefold(), "limit": limit},
            )
        return [row["id"] for row in rows]

    async def search_suggestions(
        self,
        keyword: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        keyword = self._normalize_search_keyword(keyword)
        if not keyword:
            raise ValueError("搜索关键词不能为空")
        limit = validate_limit(limit, maximum=50)
        query = """
        CALL db.index.fulltext.queryNodes($index_name, $fulltext_query)
        YIELD node, score
        WHERE node:KnowledgeNode OR node:Chapter OR node:Question
        WITH node, score
        ORDER BY score DESC, coalesce(node.name, node.title, '')
        RETURN DISTINCT coalesce(node.name, node.title) AS name,
               CASE
                   WHEN node:KnowledgeNode THEN 'KnowledgeNode'
                   WHEN node:Chapter THEN 'Chapter'
                   ELSE 'Question'
               END AS type,
               node.node_type AS sub_type,
               node.section AS section,
               score
        LIMIT $limit
        """
        rows = await self.execute_read(
            query,
            {
                "index_name": settings.NEO4J_FULLTEXT_INDEX_NAME,
                "fulltext_query": self._fulltext_query(keyword),
                "limit": limit,
            },
        )
        if rows:
            return rows
        return await self.execute_read(
            """
            MATCH (node)
            WHERE (node:KnowledgeNode OR node:Chapter OR node:Question)
              AND (
                  node.name CONTAINS $keyword
                  OR node.title CONTAINS $keyword
                  OR node.overview CONTAINS $keyword
                  OR node.category1 CONTAINS $keyword
              )
            RETURN DISTINCT coalesce(node.name, node.title) AS name,
                   CASE
                       WHEN node:KnowledgeNode THEN 'KnowledgeNode'
                       WHEN node:Chapter THEN 'Chapter'
                       ELSE 'Question'
                   END AS type,
                   node.node_type AS sub_type,
                   node.section AS section,
                   0.0 AS score
            LIMIT $limit
            """,
            {"keyword": keyword, "limit": limit},
        )

    # 按标签优先解析节点：KnowledgeNode/Question 走唯一索引 seek，
    # 其余小标签（Chapter/Category/Difficulty/NodeType）与 elementId 旧链接
    # 走兜底分支（节点量小，扫描成本可控）。
    @staticmethod
    def _node_resolution_subquery(var: str) -> str:
        return f"""
    CALL {{
        MATCH ({var}:KnowledgeNode)
        WHERE {var}.id = $id OR {var}.node_id = $id OR {var}.node_id = toInteger($id)
        RETURN {var}, 0 AS priority
        UNION ALL
        MATCH ({var}:Question)
        WHERE {var}.id = $id
        RETURN {var}, 1 AS priority
        UNION ALL
        MATCH ({var})
        WHERE NOT {var}:KnowledgeNode AND NOT {var}:Question
          AND ({var}.id = $id OR {var}.node_id = $id OR elementId({var}) = $id)
        RETURN {var}, 2 AS priority
    }}
    WITH {var}, priority
    ORDER BY priority
    LIMIT 1
    """

    async def get_node_by_id(self, node_id: str) -> Optional[Dict[str, Any]]:
        query = self._node_resolution_subquery("n") + """
        RETURN coalesce(n.id, n.node_id, elementId(n)) as id,
               labels(n)[0] as label,
               properties(n) as properties
        """
        results = await self.execute_read(query, {"id": node_id})
        if not results:
            return None
        result = results[0]
        return {
            "id": result["id"],
            "label": self._node_display_name(result["label"], result["properties"]),
            "type": result["label"],
            "properties": result["properties"],
        }

    async def get_node_relationships(
        self,
        node_id: str,
        direction: str = "both",
        limit: int = 200,
    ) -> Dict[str, Any]:
        """返回节点关系，带上限保护高度数节点（B6）。

        返回 {"relationships": [...], "truncated": bool}。
        """
        patterns = {
            "out": "(a)-[r]->(b)",
            "in": "(a)<-[r]-(b)",
            "both": "(a)-[r]-(b)",
        }
        pattern = patterns.get(direction)
        if pattern is None:
            raise ValueError("direction 必须是 in、out 或 both")
        limit = validate_limit(limit, maximum=500)
        query = self._node_resolution_subquery("a") + f"""
        MATCH {pattern}
        WITH a, r, b
        ORDER BY type(r), coalesce(b.name, b.title, b.id, '')
        LIMIT $fetch_limit
        RETURN coalesce(a.id, a.node_id, elementId(a)) as source_id,
               labels(a)[0] as source_label, properties(a) as source_props,
               type(r) as rel_type, properties(r) as rel_props,
               coalesce(b.id, b.node_id, elementId(b)) as target_id,
               labels(b)[0] as target_label, properties(b) as target_props
        """
        # 多取一条用于判断是否被截断
        results = await self.execute_read(
            query, {"id": node_id, "fetch_limit": limit + 1}
        )
        truncated = len(results) > limit
        results = results[:limit]
        relationships = [
            {
                "source": {
                    "id": result["source_id"],
                    "label": result["source_label"],
                    "name": self._node_display_name(
                        result["source_label"], result["source_props"]
                    ),
                    "properties": result["source_props"],
                },
                "target": {
                    "id": result["target_id"],
                    "label": result["target_label"],
                    "name": self._node_display_name(
                        result["target_label"], result["target_props"]
                    ),
                    "properties": result["target_props"],
                },
                "relationship": {
                    "type": result["rel_type"],
                    "properties": result["rel_props"],
                },
            }
            for result in results
        ]
        return {"relationships": relationships, "truncated": truncated}

    async def get_node_neighbors(
        self,
        node_id: str,
        limit: int = 30,
        relationship_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return a bounded graph fragment around one node."""
        limit = validate_limit(limit, maximum=100)
        query = self._node_resolution_subquery("center") + """
        MATCH (center)-[r]-(neighbor)
        WHERE (size($relationship_types) = 0 OR type(r) IN $relationship_types)
        WITH center, r, neighbor
        ORDER BY type(r), coalesce(neighbor.name, neighbor.title, neighbor.id, '')
        LIMIT $limit
        RETURN coalesce(neighbor.id, neighbor.node_id, elementId(neighbor)) AS neighbor_id,
               coalesce(neighbor.name, neighbor.title, labels(neighbor)[0]) AS neighbor_name,
               labels(neighbor)[0] AS neighbor_type,
               properties(neighbor) AS neighbor_properties,
               coalesce(startNode(r).id, startNode(r).node_id, elementId(startNode(r))) AS from_id,
               coalesce(endNode(r).id, endNode(r).node_id, elementId(endNode(r))) AS to_id,
               type(r) AS relationship_type,
               properties(r) AS relationship_properties
        """
        rows = await self.execute_read(
            query,
            {
                "id": node_id,
                "limit": limit,
                "relationship_types": relationship_types or [],
            },
        )
        nodes_by_id: Dict[str, Dict[str, Any]] = {}
        edges = []
        for row in rows:
            neighbor_id = row["neighbor_id"]
            nodes_by_id[neighbor_id] = {
                "id": neighbor_id,
                "label": self._node_display_name(
                    row["neighbor_type"], row["neighbor_properties"]
                ),
                "type": row["neighbor_type"],
                "properties": row["neighbor_properties"],
            }
            edges.append(
                {
                    "from": row["from_id"],
                    "to": row["to_id"],
                    "label": row["relationship_type"],
                    "properties": row["relationship_properties"],
                }
            )
        return {"nodes": list(nodes_by_id.values()), "edges": edges}

    async def get_graph_fragment(
        self,
        node_ids: List[str],
        relationship_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return requested business nodes and direct relationships between them."""
        requested_ids = list(dict.fromkeys(node_id.strip() for node_id in node_ids if node_id.strip()))
        if not requested_ids:
            raise ValueError("node_ids 不能为空")
        if len(requested_ids) > 200:
            raise ValueError("一次最多加载 200 个节点")

        nodes_data = await self.execute_read(
            """
            MATCH (n)
            WHERE n.id IN $node_ids OR n.node_id IN $node_ids
            RETURN coalesce(n.id, n.node_id, elementId(n)) AS id,
                   elementId(n) AS element_id,
                   labels(n)[0] AS label,
                   properties(n) AS properties
            ORDER BY coalesce(n.id, n.node_id, n.name, '')
            """,
            {"node_ids": requested_ids},
        )
        nodes = [
            {
                "id": row["id"],
                "label": self._node_display_name(row["label"], row["properties"]),
                "type": row["label"],
                "properties": row["properties"],
            }
            for row in nodes_data
        ]
        element_ids = [row["element_id"] for row in nodes_data]
        if element_ids:
            relationships = await self.execute_read(
                """
                MATCH (source)-[relationship]->(target)
                WHERE elementId(source) IN $element_ids
                  AND elementId(target) IN $element_ids
                  AND (size($relationship_types) = 0 OR type(relationship) IN $relationship_types)
                RETURN coalesce(source.id, source.node_id, elementId(source)) AS `from`,
                       coalesce(target.id, target.node_id, elementId(target)) AS `to`,
                       type(relationship) AS label,
                       properties(relationship) AS properties
                ORDER BY label, `from`, `to`
                """,
                {
                    "element_ids": element_ids,
                    "relationship_types": relationship_types or [],
                },
            )
        else:
            relationships = []

        matched_ids = {node["id"] for node in nodes}
        return {
            "nodes": nodes,
            "edges": [
                {
                    "from": row["from"],
                    "to": row["to"],
                    "label": row["label"],
                    "properties": row["properties"],
                }
                for row in relationships
            ],
            "missing_node_ids": [node_id for node_id in requested_ids if node_id not in matched_ids],
        }

    async def find_shortest_path(
        self,
        start_id: str,
        end_id: str,
        max_depth: int = 5,
    ) -> Optional[Dict[str, Any]]:
        if (
            isinstance(max_depth, bool)
            or not isinstance(max_depth, int)
            or not 1 <= max_depth <= 10
        ):
            raise ValueError("max_depth 必须在 1 到 10 之间")
        start_predicate = (
            "elementId(start) = $start_id"
            if ":" in start_id
            else "(start.id = $start_id OR start.node_id = $start_id)"
        )
        end_predicate = (
            "elementId(end) = $end_id"
            if ":" in end_id
            else "(end.id = $end_id OR end.node_id = $end_id)"
        )
        query = """
        MATCH (start:KnowledgeNode)
        WHERE {start_predicate}
        MATCH (end:KnowledgeNode)
        WHERE {end_predicate}
        MATCH path = shortestPath((start)-[:PREREQUISITE|RELATED_TO|HAS_CORE_RELATION|APPLIED_IN|HAS_INSTANCE|HAS_CORE_CONCEPT*1..{max_depth}]-(end))
        WHERE all(node IN nodes(path) WHERE node:KnowledgeNode)
        RETURN [node in nodes(path) | {{
            id: coalesce(node.id, node.node_id, elementId(node)),
            name: coalesce(node.name, node.title, ''),
            type: labels(node)[0],
            properties: properties(node)
        }}] as nodes,
        [rel in relationships(path) | {{
            type: type(rel),
            from: coalesce(startNode(rel).id, startNode(rel).node_id,
                           elementId(startNode(rel))),
            to: coalesce(endNode(rel).id, endNode(rel).node_id,
                         elementId(endNode(rel))),
            properties: properties(rel)
        }}] as relationships,
        length(path) as path_length
        LIMIT 1
        """.format(
            max_depth=max_depth,
            start_predicate=start_predicate,
            end_predicate=end_predicate,
        )
        results = await self.execute_read(
            query,
            {"start_id": start_id, "end_id": end_id},
        )
        return results[0] if results else None

    async def get_knowledge_path(
        self,
        start_knowledge: str,
        target_knowledge: str,
        max_depth: int = 5,
    ) -> Optional[Dict[str, Any]]:
        lookup_query = """
        UNWIND [
            {slot: 'start', value: $start_value},
            {slot: 'target', value: $target_value}
        ] AS requested
        CALL {
            WITH requested
            MATCH (n:KnowledgeNode)
            WHERE n.id = requested.value
               OR n.node_id = requested.value
               OR n.name = requested.value
            WITH n, requested,
                 CASE WHEN n.id = requested.value OR n.node_id = requested.value
                      THEN 0 ELSE 1 END AS priority
            ORDER BY priority, n.id
            LIMIT 1
            RETURN coalesce(n.id, n.node_id, elementId(n)) AS id
        }
        RETURN requested.slot AS slot, id
        """
        lookup_rows = await self.execute_read(
            lookup_query,
            {"start_value": start_knowledge, "target_value": target_knowledge},
        )
        resolved = {row["slot"]: row["id"] for row in lookup_rows}
        if "start" not in resolved or "target" not in resolved:
            return None
        return await self.find_shortest_path(
            resolved["start"],
            resolved["target"],
            max_depth=max_depth,
        )

    async def get_graph_data(
        self,
        limit: int = 2000,
        node_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        limit = validate_limit(limit, maximum=2000)
        safe_node_types = validate_node_labels(node_types)
        type_filter = ""
        if safe_node_types:
            type_filter = "WHERE any(label IN labels(n) WHERE label IN $node_types)"
        # Keep limited graph slices representative: every chapter gets one
        # knowledge node before the remaining capacity is filled globally.
        nodes_query = f"""
        CALL {{
            MATCH (chapter:Chapter)
            OPTIONAL MATCH (knowledge:KnowledgeNode)-[:BELONGS_TO]->(chapter)
            WITH chapter, knowledge
            ORDER BY coalesce(chapter.order, 2147483647),
                     coalesce(knowledge.node_id, knowledge.id, elementId(knowledge))
            WITH chapter, head(collect(knowledge)) AS representative
            RETURN collect(representative) AS chapter_representatives
        }}
        CALL {{
            MATCH (source)-[relationship]->(target)
            WITH type(relationship) AS relationship_type, source, target
            ORDER BY relationship_type,
                     coalesce(source.id, source.node_id, source.name, ''),
                     coalesce(target.id, target.node_id, target.name, '')
            WITH relationship_type,
                 head(collect({{
                     source: source,
                     target: target
                 }})) AS representative
            WITH collect(representative) AS representatives
            RETURN reduce(
                nodes = [],
                representative IN representatives |
                    nodes + [representative.source, representative.target]
            ) AS relationship_representatives
        }}
        CALL {{
            MATCH (difficulty:Difficulty)
            OPTIONAL MATCH (question:Question)-[:HAS_DIFFICULTY]->(difficulty)
            WITH difficulty, question
            ORDER BY coalesce(difficulty.id, difficulty.name, ''),
                     coalesce(question.id, question.node_id, question.name, '')
            WITH difficulty, head(collect(question)) AS question
            OPTIONAL MATCH (question)-[:BELONGS_TO]->(category:Category)
            WITH difficulty, question, collect(DISTINCT category) AS categories
            OPTIONAL MATCH (question)-[:REQUIRES]->(knowledge:KnowledgeNode)
            WITH difficulty, question, categories, knowledge
            ORDER BY coalesce(difficulty.id, difficulty.name, ''),
                     coalesce(knowledge.id, knowledge.node_id, knowledge.name, '')
            WITH difficulty, question, categories,
                 head(collect(knowledge)) AS knowledge
            WITH collect(difficulty) AS difficulties,
                 collect(question) AS questions,
                 collect(categories) AS category_groups,
                 collect(knowledge) AS knowledge_nodes
            RETURN difficulties + questions + knowledge_nodes +
                   reduce(
                       nodes = [],
                       categories IN category_groups | nodes + categories
                   ) AS difficulty_context
        }}
        MATCH (n)
        {type_filter}
        WITH n, chapter_representatives, relationship_representatives,
             difficulty_context,
             CASE
                 WHEN n:Chapter THEN 0
                 WHEN n IN chapter_representatives THEN 1
                 WHEN n IN relationship_representatives THEN 2
                 WHEN n IN difficulty_context THEN 3
                 WHEN n:NodeType THEN 4
                 WHEN n:KnowledgeNode THEN 5
                 WHEN n:Question THEN 6
                 WHEN n:Category THEN 7
                 WHEN n:Difficulty THEN 8
                 ELSE 9
             END AS selection_priority
        ORDER BY selection_priority,
                 coalesce(n.order, n.chapter_id, 2147483647),
                 coalesce(n.id, n.node_id, n.name, '')
        RETURN coalesce(n.id, n.node_id, elementId(n)) as id,
               elementId(n) AS element_id,
               labels(n)[0] as label,
               properties(n) as properties
        LIMIT $limit
        """
        nodes_data, statistics = await asyncio.gather(
            self.execute_read(
                nodes_query,
                {"limit": limit, "node_types": safe_node_types},
            ),
            self.get_statistics(),
        )
        nodes = [
            {
                "id": row["id"],
                "label": self._node_display_name(row["label"], row["properties"]),
                "type": row["label"],
                "properties": row["properties"],
            }
            for row in nodes_data
        ]
        node_element_ids = [row["element_id"] for row in nodes_data]
        if node_element_ids:
            rels_data = await self.execute_read(
                """
                MATCH (a)-[r]->(b)
                WHERE elementId(a) IN $element_ids
                  AND elementId(b) IN $element_ids
                RETURN coalesce(a.id, a.node_id, elementId(a)) as `from`,
                       coalesce(b.id, b.node_id, elementId(b)) as `to`,
                       type(r) as label,
                       properties(r) as properties
                """,
                {"element_ids": node_element_ids},
            )
        else:
            rels_data = []
        edges = [
            {
                "from": row["from"],
                "to": row["to"],
                "label": row["label"],
                "properties": row["properties"],
            }
            for row in rels_data
        ]
        return {
            "nodes": nodes,
            "edges": edges,
            "statistics": statistics,
        }


neo4j_service = Neo4jService()
