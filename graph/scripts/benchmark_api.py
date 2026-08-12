"""Benchmark the running API and write a low-noise JSON performance report."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

import httpx


ENDPOINTS = {
    "home": {
        "method": "GET",
        "path": "/api/v1/graph/home/data",
        "threshold_ms": 300.0,
    },
    "graph_data_300": {
        "method": "GET",
        "path": "/api/v1/graph/data?limit=300",
        "threshold_ms": 2000.0,
    },
    "search_keyword": {
        "method": "GET",
        "path": "/api/v1/search/keyword?keyword=%E5%8A%A8%E6%80%81%E8%A7%84%E5%88%92&limit=20",
        "threshold_ms": 500.0,
    },
    "shortest_path": {
        "method": "POST",
        "path": "/api/v1/path/shortest",
        "json": {"start": "NODE_002", "end": "NODE_001", "max_depth": 3},
        "threshold_ms": 1000.0,
    },
}


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentile_value) - 1)
    return ordered[index]


async def request_once(client: httpx.AsyncClient, endpoint: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = await client.request(
            endpoint["method"], endpoint["path"], json=endpoint.get("json")
        )
        duration_ms = (time.perf_counter() - started) * 1000
        return {
            "status": response.status_code,
            "duration_ms": round(duration_ms, 3),
            "response_bytes": len(response.content),
        }
    except httpx.HTTPError as exc:
        duration_ms = (time.perf_counter() - started) * 1000
        return {
            "status": 0,
            "duration_ms": round(duration_ms, 3),
            "response_bytes": 0,
            "error": type(exc).__name__,
        }


async def benchmark_endpoint(
    client: httpx.AsyncClient,
    name: str,
    endpoint: dict[str, Any],
    samples: int,
) -> dict[str, Any]:
    await request_once(client, endpoint)
    measurements = [
        await request_once(client, endpoint)
        for _ in range(samples)
    ]
    durations = [row["duration_ms"] for row in measurements]
    successful = [row for row in measurements if row["status"] == 200]
    p95 = percentile(durations, 0.95)
    return {
        "method": endpoint["method"],
        "path": endpoint["path"],
        "samples": len(measurements),
        "statuses": dict(
            sorted(
                {
                    str(status): sum(row["status"] == status for row in measurements)
                    for status in {row["status"] for row in measurements}
                }.items()
            )
        ),
        "response_bytes": max((row["response_bytes"] for row in successful), default=0),
        "p50_ms": round(statistics.median(durations), 3),
        "p95_ms": round(p95, 3),
        "max_ms": round(max(durations, default=0.0), 3),
        "threshold_ms": endpoint["threshold_ms"],
        "passed": bool(successful)
        and len(successful) == len(measurements)
        and p95 <= endpoint["threshold_ms"],
        "errors": [row["error"] for row in measurements if row.get("error")],
    }


async def benchmark_concurrency(
    client: httpx.AsyncClient,
    endpoint: dict[str, Any],
    request_count: int,
    concurrency: int,
) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(concurrency)

    async def run_limited() -> dict[str, Any]:
        async with semaphore:
            return await request_once(client, endpoint)

    measurements = await asyncio.gather(*(run_limited() for _ in range(request_count)))
    durations = [row["duration_ms"] for row in measurements]
    successful = sum(row["status"] == 200 for row in measurements)
    p95_ms = percentile(durations, 0.95)
    return {
        "requests": request_count,
        "concurrency": concurrency,
        "successful": successful,
        "failed": request_count - successful,
        "threshold_ms": 300.0,
        "p50_ms": round(percentile(durations, 0.5), 3),
        "p95_ms": round(p95_ms, 3),
        "max_ms": round(max(durations, default=0.0), 3),
        "threshold_met": p95_ms <= 300.0,
        "passed": successful == request_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--output", type=Path, default=Path("logs/api_benchmark.json"))
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict[str, Any]:
    if not 1 <= args.samples <= 100:
        raise ValueError("--samples must be between 1 and 100")
    if not 1 <= args.concurrency <= 100:
        raise ValueError("--concurrency must be between 1 and 100")
    if not 1 <= args.requests <= 1000:
        raise ValueError("--requests must be between 1 and 1000")

    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=30.0) as client:
        endpoint_results = {
            name: await benchmark_endpoint(client, name, endpoint, args.samples)
            for name, endpoint in ENDPOINTS.items()
        }
        concurrency = await benchmark_concurrency(
            client, ENDPOINTS["home"], args.requests, args.concurrency
        )
    return {
        "base_url": args.base_url.rstrip("/"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "endpoints": endpoint_results,
        "concurrency": {"home": concurrency},
        "passed": all(row["passed"] for row in endpoint_results.values())
        and concurrency["passed"],
    }


def main() -> int:
    args = parse_args()
    report = asyncio.run(run(args))
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8", newline="\n")
    temporary.replace(args.output)
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
