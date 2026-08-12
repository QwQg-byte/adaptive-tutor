"""Low-cardinality in-process runtime metrics for the API service."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from time import monotonic
from typing import Any


class RuntimeMetrics:
    """Collect basic request and Neo4j query metrics without user data."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with getattr(self, "_lock", Lock()):
            self._started_at = monotonic()
            self._in_flight = 0
            self._request_count = 0
            self._request_errors = 0
            self._request_total_ms = 0.0
            self._request_max_ms = 0.0
            self._request_slow = 0
            self._status_codes: dict[str, int] = defaultdict(int)
            self._routes: dict[str, dict[str, float | int]] = defaultdict(
                lambda: {
                    "count": 0,
                    "errors": 0,
                    "slow": 0,
                    "total_ms": 0.0,
                    "max_ms": 0.0,
                }
            )
            self._query_count = 0
            self._query_errors = 0
            self._query_slow = 0
            self._query_total_ms = 0.0
            self._query_max_ms = 0.0
            self._query_modes: dict[str, int] = defaultdict(int)

    def begin_request(self) -> None:
        with self._lock:
            self._in_flight += 1

    def finish_request(
        self,
        route: str,
        status_code: int,
        duration_ms: float,
        *,
        slow: bool,
    ) -> None:
        route = route or "unknown"
        is_error = status_code >= 500
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            self._request_count += 1
            self._request_errors += int(is_error)
            self._request_slow += int(slow)
            self._request_total_ms += duration_ms
            self._request_max_ms = max(self._request_max_ms, duration_ms)
            self._status_codes[str(status_code)] += 1
            bucket = self._routes[route]
            bucket["count"] += 1
            bucket["errors"] += int(is_error)
            bucket["slow"] += int(slow)
            bucket["total_ms"] += duration_ms
            bucket["max_ms"] = max(float(bucket["max_ms"]), duration_ms)

    def record_query(
        self,
        mode: str,
        duration_ms: float,
        *,
        failed: bool,
        slow: bool,
    ) -> None:
        normalized_mode = mode.lower()
        with self._lock:
            self._query_count += 1
            self._query_errors += int(failed)
            self._query_slow += int(slow)
            self._query_total_ms += duration_ms
            self._query_max_ms = max(self._query_max_ms, duration_ms)
            self._query_modes[normalized_mode] += 1

    @staticmethod
    def _average(total_ms: float, count: int) -> float:
        return round(total_ms / count, 3) if count else 0.0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            routes = {
                route: {
                    "count": int(bucket["count"]),
                    "errors": int(bucket["errors"]),
                    "slow": int(bucket["slow"]),
                    "average_ms": self._average(
                        float(bucket["total_ms"]), int(bucket["count"])
                    ),
                    "max_ms": round(float(bucket["max_ms"]), 3),
                }
                for route, bucket in sorted(self._routes.items())
            }
            return {
                "uptime_seconds": round(monotonic() - self._started_at, 3),
                "requests": {
                    "in_flight": self._in_flight,
                    "count": self._request_count,
                    "errors": self._request_errors,
                    "slow": self._request_slow,
                    "average_ms": self._average(
                        self._request_total_ms, self._request_count
                    ),
                    "max_ms": round(self._request_max_ms, 3),
                    "status_codes": dict(sorted(self._status_codes.items())),
                    "routes": routes,
                },
                "neo4j_queries": {
                    "count": self._query_count,
                    "errors": self._query_errors,
                    "slow": self._query_slow,
                    "average_ms": self._average(
                        self._query_total_ms, self._query_count
                    ),
                    "max_ms": round(self._query_max_ms, 3),
                    "modes": dict(sorted(self._query_modes.items())),
                },
            }


runtime_metrics = RuntimeMetrics()
