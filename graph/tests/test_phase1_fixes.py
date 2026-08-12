"""阶段 1（2026-07-21 Claude 接手升级）修复项的回归测试。

覆盖：
- B4 未匹配路由的指标桶名统一为 unmatched（防基数爆炸）；
- B5 应用层限速器与安全响应头；
- B6 节点关系查询上限与截断标记；
- B7/B16 节点解析查询按标签寻址并兼容数字 node_id 双形态；
- Q6 遗留测试端点已移除。
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from main import app
from middleware import SECURITY_HEADERS, FixedWindowRateLimiter
from observability import runtime_metrics
from database.neo4j_service import Neo4jService


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


@pytest.mark.asyncio
async def test_unmatched_routes_share_one_metrics_bucket(client):
    """B4: 任意不存在的路径都记入 unmatched，不以原始 URL 建桶。"""
    runtime_metrics.reset()

    await client.get("/no-such-path-1")
    await client.get("/another/random/path?x=1")
    metrics = await client.get("/metrics")

    routes = metrics.json()["requests"]["routes"]
    assert "unmatched" in routes
    assert routes["unmatched"]["count"] >= 2
    assert "/no-such-path-1" not in routes
    assert "/another/random/path" not in routes


@pytest.mark.asyncio
async def test_security_headers_present_without_nginx(client):
    """B5: 直连应用层也带安全响应头。"""
    response = await client.get("/health")

    for header, value in SECURITY_HEADERS.items():
        assert response.headers.get(header) == value


def test_rate_limiter_blocks_after_limit_and_recovers():
    """B5: 固定窗口限速器超限拒绝，窗口过期后恢复。"""
    limiter = FixedWindowRateLimiter(limit_per_window=3, window_seconds=60.0)

    assert all(limiter.allow("1.2.3.4") for _ in range(3))
    assert not limiter.allow("1.2.3.4")
    # 其他客户端不受影响
    assert limiter.allow("5.6.7.8")


def test_rate_limiter_memory_stays_bounded():
    """B5: 客户端数量超过容量时淘汰而不是无界增长。"""
    limiter = FixedWindowRateLimiter(
        limit_per_window=10, window_seconds=60.0, max_clients=100
    )
    for index in range(500):
        limiter.allow(f"10.0.0.{index}")

    assert len(limiter._clients) <= 100 + 1


@pytest.mark.asyncio
async def test_node_relationships_truncated_flag():
    """B6: 超出上限时截断并标记 truncated。"""
    service = Neo4jService()
    row = {
        "source_id": "NODE_001",
        "source_label": "KnowledgeNode",
        "source_props": {"name": "源"},
        "rel_type": "REQUIRES",
        "rel_props": {},
        "target_id": "NODE_002",
        "target_label": "KnowledgeNode",
        "target_props": {"name": "目标"},
    }
    with patch.object(
        service, "execute_read", new=AsyncMock(return_value=[dict(row)] * 201)
    ) as mock_read:
        result = await service.get_node_relationships("NODE_001", limit=200)

    assert result["truncated"] is True
    assert len(result["relationships"]) == 200
    # 多取一条用于判断截断
    assert mock_read.await_args.args[1]["fetch_limit"] == 201


@pytest.mark.asyncio
async def test_node_relationships_not_truncated_below_limit():
    service = Neo4jService()
    with patch.object(service, "execute_read", new=AsyncMock(return_value=[])):
        result = await service.get_node_relationships("NODE_001")

    assert result == {"relationships": [], "truncated": False}


def test_node_resolution_subquery_uses_labels_and_integer_fallback():
    """B7/B16: 解析子查询按标签寻址，且兼容整数形态的 node_id。"""
    subquery = Neo4jService._node_resolution_subquery("n")

    assert "MATCH (n:KnowledgeNode)" in subquery
    assert "MATCH (n:Question)" in subquery
    assert "toInteger($id)" in subquery
    assert "NOT n:KnowledgeNode AND NOT n:Question" in subquery


@pytest.mark.asyncio
async def test_legacy_test_endpoint_removed(client):
    """Q6: /graph/test-endpoint 已删除。"""
    response = await client.get("/api/v1/graph/test-endpoint")

    assert response.status_code == 404
