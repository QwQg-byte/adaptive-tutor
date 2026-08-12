"""Neo4j 连接配置，只从环境变量或本机 .env 读取凭据。"""

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / "application" / "backend" / ".env")

password = os.getenv("NEO4J_PASSWORD", "").strip()
if not password:
    raise RuntimeError(
        "缺少 NEO4J_PASSWORD，请在 application/backend/.env 中配置，"
        "不要把真实密码写入源码"
    )

# Neo4j连接配置
NEO4J_CONFIG = {
    "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    "user": os.getenv("NEO4J_USER", "neo4j"),
    "password": password,
    "database": os.getenv("NEO4J_DATABASE", "neo4j"),
    "max_connection_pool_size": int(
        os.getenv("NEO4J_MAX_CONNECTION_POOL_SIZE", "50")
    ),
    "connection_timeout": float(
        os.getenv("NEO4J_CONNECTION_TIMEOUT_SECONDS", "10")
    ),
    "connection_acquisition_timeout": float(
        os.getenv("NEO4J_CONNECTION_ACQUISITION_TIMEOUT_SECONDS", "30")
    ),
    "max_connection_lifetime": float(
        os.getenv("NEO4J_MAX_CONNECTION_LIFETIME_SECONDS", "3600")
    ),
    "max_transaction_retry_time": float(
        os.getenv("NEO4J_MAX_TRANSACTION_RETRY_TIME_SECONDS", "15")
    ),
    "query_timeout": float(os.getenv("NEO4J_QUERY_TIMEOUT_SECONDS", "30")),
}

# 使用方法：
# 1. 在 application/backend/.env 中配置连接信息
# 2. 在代码中使用：
#    from config_neo4j import NEO4J_CONFIG
#    connector = Neo4jConnector(
#        uri=NEO4J_CONFIG["uri"],
#        user=NEO4J_CONFIG["user"],
#        password=NEO4J_CONFIG["password"]
#    )
