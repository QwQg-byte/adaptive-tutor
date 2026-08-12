"""Deterministic learning-plan ordering and recommendation contracts."""

from unittest.mock import AsyncMock, patch

import pytest

from api.path import _fetch_questions_for_nodes, _prune_and_sort


def test_prune_and_sort_places_prerequisites_before_target():
    target = {"id": "TARGET", "name": "目标"}
    nodes = {
        "BASE": {"id": "BASE", "name": "基础", "depth": 2},
        "MID": {"id": "MID", "name": "中间", "depth": 1},
    }
    edges = [("TARGET", "MID"), ("MID", "BASE")]

    ordered, skipped, dependencies = _prune_and_sort(target, nodes, edges, set())

    assert ordered == ["BASE", "MID", "TARGET"]
    assert skipped == set()
    assert dependencies["TARGET"] == ["MID"]


def test_prune_and_sort_prunes_mastered_branch_and_breaks_cycles_stably():
    target = {"id": "TARGET", "name": "目标"}
    nodes = {
        "A": {"id": "A", "name": "A", "depth": 1},
        "B": {"id": "B", "name": "B", "depth": 2},
        "MASTERED": {"id": "MASTERED", "name": "已掌握", "depth": 1},
        "HIDDEN": {"id": "HIDDEN", "name": "被裁剪", "depth": 2},
    }
    edges = [
        ("TARGET", "A"),
        ("A", "B"),
        ("B", "A"),
        ("TARGET", "MASTERED"),
        ("MASTERED", "HIDDEN"),
    ]

    ordered, skipped, _ = _prune_and_sort(
        target, nodes, edges, {"MASTERED"}
    )

    assert ordered[-1] == "TARGET"
    assert set(ordered) == {"A", "B", "TARGET"}
    assert skipped == {"MASTERED"}
    assert "HIDDEN" not in ordered


@pytest.mark.asyncio
async def test_recommendations_pass_preference_and_stable_limit_to_query():
    rows = [{"kid": "NODE_1", "questions": [{"id": "Q1"}]}]
    execute = AsyncMock(return_value=rows)

    with patch("api.path.neo4j_service.execute_query", execute):
        result = await _fetch_questions_for_nodes(
            ["NODE_1"], 3, difficulty_preference="challenge"
        )

    assert result == {"NODE_1": [{"id": "Q1"}]}
    query, parameters = execute.await_args.args
    assert "q.id ASC" in query
    assert parameters == {
        "ids": ["NODE_1"],
        "per_node": 3,
        "difficulty_preference": "challenge",
    }
