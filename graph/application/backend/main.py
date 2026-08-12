"""
FastAPI主应用入口
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from contextlib import asynccontextmanager
from ipaddress import ip_address
from loguru import logger
import sys
from time import perf_counter
from config import settings
from database.neo4j_service import neo4j_service
from database.neo4j_exceptions import (
    Neo4jConnectionError,
    Neo4jQueryError,
    Neo4jQueryTimeoutError,
)
from observability import runtime_metrics
from middleware import FixedWindowRateLimiter, SECURITY_HEADERS

# 导入路由
from api import graph, search, path


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info(f"启动 {settings.APP_NAME} v{settings.APP_VERSION}")
    try:
        await neo4j_service.connect()
        logger.info("Neo4j连接成功")
        # Warm the merged metadata query and cache during startup so the first
        # graph page request does not pay the driver's initial query cost.
        try:
            await neo4j_service.get_statistics(force_refresh=True)
        except (Neo4jQueryError, Neo4jQueryTimeoutError):
            logger.warning("图谱统计缓存预热失败，首次请求将重试")
        else:
            logger.info("图谱统计缓存预热完成")
    except Neo4jConnectionError:
        logger.warning("Neo4j连接失败，数据库接口将返回 503")

    try:
        yield
    finally:
        logger.info("关闭应用...")
        await neo4j_service.close()


# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="知识图谱可视化与智能查询系统",
    debug=settings.DEBUG,
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type"],
)


@app.middleware("http")
async def collect_runtime_metrics(request: Request, call_next):
    """Record bounded request metrics and expose timing in a response header."""
    if request.url.path == "/metrics":
        return await call_next(request)
    runtime_metrics.begin_request()
    started = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration_ms = (perf_counter() - started) * 1000
        route = request.scope.get("route")
        # 未匹配到已注册路由时统一记为 unmatched，避免用原始 URL
        # （攻击者可控）作为指标桶名导致基数与内存无界增长。
        route_path = getattr(route, "path", None) or "unmatched"
        slow = duration_ms >= settings.SLOW_REQUEST_THRESHOLD_MS
        runtime_metrics.finish_request(
            route_path,
            status_code,
            duration_ms,
            slow=slow,
        )
        if "response" in locals():
            response.headers["X-Process-Time-Ms"] = f"{duration_ms:.3f}"
        if slow:
            logger.warning(
                "Slow API request: method={} route={} status={} duration_ms={:.3f} threshold_ms={:.3f}",
                request.method,
                route_path,
                status_code,
                duration_ms,
                settings.SLOW_REQUEST_THRESHOLD_MS,
            )


_rate_limiter = FixedWindowRateLimiter(
    limit_per_window=settings.RATE_LIMIT_PER_MINUTE,
    window_seconds=60.0,
    max_clients=settings.RATE_LIMIT_MAX_CLIENTS,
)


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    """应用层纵深防御：限速 + 安全响应头（不依赖 Nginx）。"""
    if settings.RATE_LIMIT_ENABLED and request.url.path not in (
        "/health",
        "/health/live",
        "/health/ready",
    ):
        client_host = request.client.host if request.client else "unknown"
        if not _rate_limiter.allow(client_host):
            response = JSONResponse(
                status_code=429,
                content={"success": False, "message": "请求过于频繁，请稍后再试", "data": None},
            )
            response.headers.update(SECURITY_HEADERS)
            return response
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response

# 注册路由
app.include_router(graph.router, prefix=settings.API_PREFIX)
app.include_router(search.router, prefix=settings.API_PREFIX)
app.include_router(path.router, prefix=settings.API_PREFIX)


def database_error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message, "data": None},
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    response = database_error_response(exc.status_code, str(exc.detail))
    if exc.headers:
        response.headers.update(exc.headers)
    return response


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return database_error_response(422, "请求参数校验失败")


@app.exception_handler(Neo4jConnectionError)
async def handle_neo4j_connection_error(
    request: Request,
    exc: Neo4jConnectionError,
) -> JSONResponse:
    logger.error("Neo4j unavailable for {} {}", request.method, request.url.path)
    return database_error_response(503, "数据库暂时不可用")


@app.exception_handler(Neo4jQueryTimeoutError)
async def handle_neo4j_timeout(
    request: Request,
    exc: Neo4jQueryTimeoutError,
) -> JSONResponse:
    logger.error("Neo4j timeout for {} {}", request.method, request.url.path)
    return database_error_response(504, "数据库查询超时")


@app.exception_handler(Neo4jQueryError)
async def handle_neo4j_query_error(
    request: Request,
    exc: Neo4jQueryError,
) -> JSONResponse:
    logger.error("Neo4j query failure for {} {}", request.method, request.url.path)
    return database_error_response(500, "数据库查询失败")


# 配置日志
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=settings.LOG_LEVEL
)
if settings.LOG_FILE:
    def _rotate_daily_or_100mb(message, file):
        """按天轮转，同时以 100MB 兜底，防止突发日志撑爆磁盘。"""
        if file.tell() + len(message) > 100 * 1024 * 1024:
            return True
        record_date = message.record["time"].date()
        if not hasattr(file, "_kg_open_date"):
            file._kg_open_date = record_date
        if record_date != file._kg_open_date:
            file._kg_open_date = record_date
            return True
        return False

    logger.add(
        settings.LOG_FILE,
        rotation=_rotate_daily_or_100mb,
        retention="7 days",
        level=settings.LOG_LEVEL,
        enqueue=True  # 多进程安全写入
    )


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": f"欢迎使用 {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health")
async def health_check():
    """健康检查（兼容旧调用方，等价于 /health/ready）"""
    return await health_ready()


@app.get("/health/live")
async def health_live():
    """存活探针：只确认进程在响应请求，不查询数据库。"""
    return {"status": "alive"}


@app.get("/health/ready")
async def health_ready():
    """就绪探针：实际 ping Neo4j，确认可以处理业务请求。"""
    neo4j_connected = await neo4j_service.ping()
    return {
        "status": "healthy" if neo4j_connected else "degraded",
        "neo4j_connected": neo4j_connected,
    }


def _is_local_or_private(client_host: str) -> bool:
    try:
        addr = ip_address(client_host)
    except ValueError:
        return False
    return addr.is_loopback or addr.is_private


def _snapshot_to_prometheus(snapshot: dict) -> str:
    """Render the metrics snapshot as Prometheus text exposition format."""
    lines: list[str] = []
    requests = snapshot["requests"]
    lines.append("# HELP kg_uptime_seconds Process uptime in seconds.")
    lines.append("# TYPE kg_uptime_seconds gauge")
    lines.append(f"kg_uptime_seconds {snapshot['uptime_seconds']}")

    lines.append("# HELP kg_requests_in_flight Requests currently being processed.")
    lines.append("# TYPE kg_requests_in_flight gauge")
    lines.append(f"kg_requests_in_flight {requests['in_flight']}")

    lines.append("# HELP kg_requests_total Total HTTP requests handled.")
    lines.append("# TYPE kg_requests_total counter")
    lines.append(f"kg_requests_total {requests['count']}")

    lines.append("# HELP kg_request_errors_total HTTP requests that returned 5xx.")
    lines.append("# TYPE kg_request_errors_total counter")
    lines.append(f"kg_request_errors_total {requests['errors']}")

    lines.append("# HELP kg_request_duration_ms_avg Average request duration in milliseconds.")
    lines.append("# TYPE kg_request_duration_ms_avg gauge")
    lines.append(f"kg_request_duration_ms_avg {requests['average_ms']}")

    lines.append("# HELP kg_route_requests_total Requests per route.")
    lines.append("# TYPE kg_route_requests_total counter")
    for route, bucket in requests["routes"].items():
        route_label = route.replace('"', '\\"')
        lines.append(f'kg_route_requests_total{{route="{route_label}"}} {bucket["count"]}')

    queries = snapshot["neo4j_queries"]
    lines.append("# HELP kg_neo4j_queries_total Total Neo4j queries executed.")
    lines.append("# TYPE kg_neo4j_queries_total counter")
    lines.append(f"kg_neo4j_queries_total {queries['count']}")

    lines.append("# HELP kg_neo4j_query_errors_total Neo4j queries that raised an error.")
    lines.append("# TYPE kg_neo4j_query_errors_total counter")
    lines.append(f"kg_neo4j_query_errors_total {queries['errors']}")

    return "\n".join(lines) + "\n"


@app.get("/metrics")
async def metrics(request: Request, format: str = "json"):
    """Return process-local operational metrics without request payloads.

    Restricted to loopback/private callers: this is an ops-only surface and
    should never be reachable from the public internet, even if a future
    reverse-proxy change accidentally forwards it.
    """
    client_host = request.client.host if request.client else ""
    if not _is_local_or_private(client_host):
        raise HTTPException(status_code=403, detail="仅允许内网访问")
    snapshot = runtime_metrics.snapshot()
    if format == "prometheus":
        return PlainTextResponse(
            _snapshot_to_prometheus(snapshot),
            media_type="text/plain; version=0.0.4",
        )
    return snapshot


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower()
    )
