"""应用层纵深防御中间件：限速与安全响应头。

Nginx 层已有 limit_req 和安全响应头，但直连 FastAPI 端口时它们不生效。
这里提供进程内的第二道防线：
- 每客户端 IP 固定窗口限速，内存有界（超过容量时优先淘汰最旧窗口的记录）；
- 所有响应统一附加基础安全响应头。

不引入外部依赖；多 worker 部署时每个进程独立计数，阈值按单进程理解。
"""

from __future__ import annotations

from threading import Lock
from time import monotonic


class FixedWindowRateLimiter:
    """按客户端标识的固定窗口限速器，内存有界。"""

    def __init__(
        self,
        limit_per_window: int,
        window_seconds: float = 60.0,
        max_clients: int = 10000,
    ) -> None:
        self._limit = max(1, int(limit_per_window))
        self._window_seconds = window_seconds
        self._max_clients = max(100, int(max_clients))
        self._lock = Lock()
        # client_id -> (window_start_monotonic, count)
        self._clients: dict[str, tuple[float, int]] = {}

    def allow(self, client_id: str) -> bool:
        now = monotonic()
        with self._lock:
            entry = self._clients.get(client_id)
            if entry is None or now - entry[0] >= self._window_seconds:
                if len(self._clients) >= self._max_clients:
                    self._evict_expired_locked(now)
                self._clients[client_id] = (now, 1)
                return True
            window_start, count = entry
            if count >= self._limit:
                return False
            self._clients[client_id] = (window_start, count + 1)
            return True

    def _evict_expired_locked(self, now: float) -> None:
        expired = [
            key
            for key, (window_start, _) in self._clients.items()
            if now - window_start >= self._window_seconds
        ]
        for key in expired:
            del self._clients[key]
        if len(self._clients) >= self._max_clients:
            # 极端情况下（全部未过期）淘汰窗口最旧的一批，保持内存有界
            oldest = sorted(
                self._clients.items(), key=lambda item: item[1][0]
            )[: max(1, self._max_clients // 10)]
            for key, _ in oldest:
                del self._clients[key]


SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # API 服务只返回 JSON，保守 CSP 防止响应被当作页面渲染
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}
