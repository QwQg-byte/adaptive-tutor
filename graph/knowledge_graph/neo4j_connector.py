"""
Neo4j连接器 - 知识图谱数据库连接和操作
"""

from neo4j import GraphDatabase, READ_ACCESS, WRITE_ACCESS, unit_of_work
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from typing import Any, Dict, List, Optional
import logging
import re

try:
    from .cypher_security import (
        validate_node_label,
        validate_property_name,
        validate_property_names,
        validate_relationship_type,
    )
    from .neo4j_exceptions import (
        Neo4jConnectionError,
        Neo4jQueryError,
        Neo4jQueryTimeoutError,
    )
except ImportError:
    from cypher_security import (
        validate_node_label,
        validate_property_name,
        validate_property_names,
        validate_relationship_type,
    )
    from neo4j_exceptions import (
        Neo4jConnectionError,
        Neo4jQueryError,
        Neo4jQueryTimeoutError,
    )

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCHEMA_OBJECT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_schema_object_name(name: str) -> str:
    """Validate named Neo4j 5 constraints and indexes before interpolation."""
    if not SCHEMA_OBJECT_NAME_PATTERN.fullmatch(name):
        raise ValueError(f"非法 Schema 对象名: {name}")
    return name


class Neo4jConnector:
    """Neo4j数据库连接器"""

    def __init__(
        self,
        uri: str = None,
        user: str = None,
        password: str = None,
        database: str = None,
    ):
        """
        初始化Neo4j连接器
        
        Args:
            uri: Neo4j数据库URI，默认从配置文件读取或使用bolt://localhost:7687
            user: 用户名，默认从配置文件读取或使用neo4j
            password: 密码，必须通过参数、环境变量或本机 .env 提供
        """
        # 尝试从配置文件读取默认值
        config = self._load_config()
        
        self.uri = uri if uri is not None else config.get("uri", "bolt://localhost:7687")
        self.user = user if user is not None else config.get("user", "neo4j")
        self.password = password if password is not None else config.get("password")
        self.database = database if database is not None else config.get("database", "neo4j")
        self.max_connection_pool_size = int(config.get("max_connection_pool_size", 50))
        self.connection_timeout = float(config.get("connection_timeout", 10))
        self.connection_acquisition_timeout = float(
            config.get("connection_acquisition_timeout", 30)
        )
        self.max_connection_lifetime = float(config.get("max_connection_lifetime", 3600))
        self.max_transaction_retry_time = float(
            config.get("max_transaction_retry_time", 15)
        )
        self.query_timeout = float(config.get("query_timeout", 30))
        if not self.password:
            raise ValueError("缺少 Neo4j 密码，禁止使用默认密码")
        positive_settings = {
            "max_connection_pool_size": self.max_connection_pool_size,
            "connection_timeout": self.connection_timeout,
            "connection_acquisition_timeout": self.connection_acquisition_timeout,
            "max_connection_lifetime": self.max_connection_lifetime,
            "query_timeout": self.query_timeout,
        }
        invalid = [name for name, value in positive_settings.items() if value <= 0]
        if invalid:
            raise ValueError(f"Neo4j 配置必须大于 0: {', '.join(invalid)}")
        if self.max_transaction_retry_time < 0:
            raise ValueError("Neo4j max_transaction_retry_time 不能小于 0")
        self.driver = None
        self.connect()

    def _load_config(self) -> Dict[str, Any]:
        """
        从配置文件加载Neo4j连接配置
        
        Returns:
            配置字典
        """
        config = {}
        try:
            # 尝试导入配置文件
            try:
                from .config_neo4j import NEO4J_CONFIG
            except ImportError:
                from config_neo4j import NEO4J_CONFIG
            config = NEO4J_CONFIG
            logger.info("已从配置文件加载Neo4j连接配置")
        except ImportError:
            logger.warning("未找到配置文件 config_neo4j.py，使用默认配置")
        return config

    def connect(self) -> None:
        """
        连接到Neo4j数据库
        
        Raises:
            Neo4jConnectionError: 连接或认证失败
        """
        if self.driver is not None:
            return
        driver = None
        try:
            driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                max_connection_pool_size=self.max_connection_pool_size,
                connection_timeout=self.connection_timeout,
                connection_acquisition_timeout=self.connection_acquisition_timeout,
                max_connection_lifetime=self.max_connection_lifetime,
                max_transaction_retry_time=self.max_transaction_retry_time,
                keep_alive=True,
            )
            driver.verify_connectivity()
        except Exception as exc:
            if driver is not None:
                driver.close()
            logger.error("连接 Neo4j 失败: %s", type(exc).__name__)
            raise Neo4jConnectionError("无法连接 Neo4j 数据库") from exc
        self.driver = driver
        logger.info("成功连接 Neo4j 数据库: %s / %s", self.uri, self.database)
    
    def close(self):
        """关闭数据库连接"""
        if self.driver:
            driver = self.driver
            self.driver = None
            driver.close()
            logger.info("Neo4j数据库连接已关闭")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    @staticmethod
    def _is_timeout(exc: Exception) -> bool:
        code = str(getattr(exc, "code", ""))
        name = type(exc).__name__
        return (
            isinstance(exc, TimeoutError)
            or "Timeout" in name
            or "TimedOut" in code
            or "Timeout" in code
        )

    def _execute(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]],
        access_mode: str,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        if not self.driver:
            raise Neo4jConnectionError("Neo4j 数据库未连接")
        query_timeout = self.query_timeout if timeout is None else timeout
        if query_timeout <= 0:
            raise ValueError("query timeout 必须大于 0")

        def run_query(transaction):
            result = transaction.run(
                query,
                parameters or {},
            )
            return [record.data() for record in result]

        transaction_work = unit_of_work(timeout=query_timeout)(run_query)

        try:
            with self.driver.session(
                database=self.database,
                default_access_mode=access_mode,
            ) as session:
                if access_mode == READ_ACCESS:
                    return session.execute_read(transaction_work)
                return session.execute_write(transaction_work)
        except Exception as exc:
            if self._is_timeout(exc):
                logger.error("Neo4j 查询超时: %s", type(exc).__name__)
                raise Neo4jQueryTimeoutError("Neo4j 查询超时") from exc
            if isinstance(exc, (ServiceUnavailable, SessionExpired)):
                logger.error("Neo4j 连接中断: %s", type(exc).__name__)
                raise Neo4jConnectionError("Neo4j 数据库不可用") from exc
            logger.error("Neo4j 查询失败: %s", type(exc).__name__)
            raise Neo4jQueryError("Neo4j 查询执行失败") from exc

    def execute_read(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        return self._execute(query, parameters, READ_ACCESS, timeout)

    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Compatibility alias for read-only tooling queries."""
        return self.execute_read(query, parameters, timeout=timeout)

    def execute_write_records(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        return self._execute(query, parameters, WRITE_ACCESS, timeout)

    def execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> bool:
        self.execute_write_records(query, parameters, timeout=timeout)
        return True
    
    # ============ 节点操作 ============
    
    def create_node(self, label: str, properties: Dict[str, Any]) -> Optional[Dict]:
        """
        创建节点
        
        Args:
            label: 节点标签
            properties: 节点属性
        
        Returns:
            创建的节点信息
        """
        label = validate_node_label(label)
        validate_property_names(properties.keys())
        query = f"""
        CREATE (n:{label} $properties)
        RETURN n
        """
        result = self.execute_write_records(query, {"properties": properties})
        return result[0]['n'] if result else None
    
    def create_nodes_batch(self, label: str, nodes_list: List[Dict[str, Any]]) -> int:
        """
        批量创建节点
        
        Args:
            label: 节点标签
            nodes_list: 节点属性列表
        
        Returns:
            创建的节点数量
        """
        label = validate_node_label(label)
        for node in nodes_list:
            validate_property_names(node.keys())
        query = f"""
        UNWIND $nodes AS node
        CREATE (n:{label})
        SET n = node
        RETURN count(n) as count
        """
        result = self.execute_write_records(query, {"nodes": nodes_list})
        return result[0]['count'] if result else 0
    
    def get_node(self, label: str, property_name: str, property_value: Any) -> Optional[Dict]:
        """
        根据属性获取节点
        
        Args:
            label: 节点标签
            property_name: 属性名
            property_value: 属性值
        
        Returns:
            节点信息
        """
        label = validate_node_label(label)
        property_name = validate_property_name(property_name)
        query = f"""
        MATCH (n:{label} {{{property_name}: $value}})
        RETURN n
        """
        result = self.execute_query(query, {"value": property_value})
        return result[0]['n'] if result else None
    
    def get_all_nodes(self, label: str = None) -> List[Dict]:
        """
        获取所有节点
        
        Args:
            label: 节点标签，None表示所有节点
        
        Returns:
            节点列表
        """
        if label:
            label = validate_node_label(label)
            query = f"MATCH (n:{label}) RETURN n"
        else:
            query = "MATCH (n) RETURN n"
        
        result = self.execute_query(query)
        return [record['n'] for record in result]
    
    def update_node(self, label: str, property_name: str, property_value: Any, 
                    updates: Dict[str, Any]) -> bool:
        """
        更新节点
        
        Args:
            label: 节点标签
            property_name: 属性名
            property_value: 属性值
            updates: 更新的属性
        
        Returns:
            是否成功
        """
        label = validate_node_label(label)
        property_name = validate_property_name(property_name)
        validate_property_names(updates.keys())
        query = f"""
        MATCH (n:{label} {{{property_name}: $value}})
        SET n += $updates
        RETURN n
        """
        result = self.execute_write_records(
            query,
            {"value": property_value, "updates": updates},
        )
        return len(result) > 0
    
    def delete_node(self, label: str, property_name: str, property_value: Any) -> bool:
        """
        删除节点及其关系
        
        Args:
            label: 节点标签
            property_name: 属性名
            property_value: 属性值
        
        Returns:
            是否成功
        """
        label = validate_node_label(label)
        property_name = validate_property_name(property_name)
        query = f"""
        MATCH (n:{label} {{{property_name}: $value}})
        DETACH DELETE n
        RETURN count(n) as count
        """
        result = self.execute_write_records(query, {"value": property_value})
        return result[0]['count'] > 0 if result else False
    
    # ============ 关系操作 ============
    
    def create_relationship(self, source_label: str, source_prop: str, source_value: Any,
                           target_label: str, target_prop: str, target_value: Any,
                           rel_type: str, properties: Dict[str, Any] = None) -> bool:
        """
        创建关系
        
        Args:
            source_label: 源节点标签
            source_prop: 源节点属性名
            source_value: 源节点属性值
            target_label: 目标节点标签
            target_prop: 目标节点属性名
            target_value: 目标节点属性值
            rel_type: 关系类型
            properties: 关系属性
        
        Returns:
            是否成功
        """
        source_label = validate_node_label(source_label)
        source_prop = validate_property_name(source_prop)
        target_label = validate_node_label(target_label)
        target_prop = validate_property_name(target_prop)
        rel_type = validate_relationship_type(rel_type)
        validate_property_names((properties or {}).keys())
        query = f"""
        MATCH (s:{source_label} {{{source_prop}: $source_value}})
        MATCH (t:{target_label} {{{target_prop}: $target_value}})
        CREATE (s)-[r:{rel_type}]->(t)
        SET r += $properties
        RETURN r
        """
        result = self.execute_write_records(query, {
            "source_value": source_value,
            "target_value": target_value,
            "properties": properties or {}
        })
        return len(result) > 0
    
    def create_relationships_batch(self, relationships: List[Dict[str, Any]]) -> int:
        """
        批量创建关系
        
        Args:
            relationships: 关系列表，每个关系包含source_label, source_prop, source_value,
                         target_label, target_prop, target_value, rel_type, properties
        
        Returns:
            创建的关系数量
        """
        created = 0
        for rel in relationships:
            if self.create_relationship(
                rel["source_label"],
                rel["source_prop"],
                rel["source_value"],
                rel["target_label"],
                rel["target_prop"],
                rel["target_value"],
                rel["rel_type"],
                rel.get("properties"),
            ):
                created += 1
        return created
    
    def get_relationships(self, label: str = None, rel_type: str = None) -> List[Dict]:
        """
        获取关系
        
        Args:
            label: 节点标签
            rel_type: 关系类型
        
        Returns:
            关系列表
        """
        if label:
            label = validate_node_label(label)
        if rel_type:
            rel_type = validate_relationship_type(rel_type)

        if label and rel_type:
            query = f"MATCH (s:{label})-[r:{rel_type}]->(t) RETURN s, r, t"
        elif label:
            query = f"MATCH (s:{label})-[r]->(t) RETURN s, r, t"
        elif rel_type:
            query = f"MATCH (s)-[r:{rel_type}]->(t) RETURN s, r, t"
        else:
            query = "MATCH (s)-[r]->(t) RETURN s, r, t"
        
        result = self.execute_query(query)
        return result
    
    def delete_relationship(self, source_label: str, source_prop: str, source_value: Any,
                           target_label: str, target_prop: str, target_value: Any,
                           rel_type: str) -> bool:
        """
        删除关系
        
        Args:
            source_label: 源节点标签
            source_prop: 源节点属性名
            source_value: 源节点属性值
            target_label: 目标节点标签
            target_prop: 目标节点属性名
            target_value: 目标节点属性值
            rel_type: 关系类型
        
        Returns:
            是否成功
        """
        source_label = validate_node_label(source_label)
        source_prop = validate_property_name(source_prop)
        target_label = validate_node_label(target_label)
        target_prop = validate_property_name(target_prop)
        rel_type = validate_relationship_type(rel_type)
        query = f"""
        MATCH (s:{source_label} {{{source_prop}: $source_value}})-[r:{rel_type}]->(t:{target_label} {{{target_prop}: $target_value}})
        DELETE r
        RETURN count(r) as count
        """
        result = self.execute_write_records(query, {
            "source_value": source_value,
            "target_value": target_value
        })
        return result[0]['count'] > 0 if result else False
    
    # ============ 索引和约束 ============
    
    def create_constraint(
        self,
        label: str,
        property_name: str,
        constraint_type: str = "unique",
        name: str = None,
    ) -> bool:
        """
        创建约束
        
        Args:
            label: 节点标签
            property_name: 属性名
            constraint_type: 约束类型 (unique, exists)
        
        Returns:
            是否成功
        """
        label = validate_node_label(label)
        property_name = validate_property_name(property_name)
        suffix = "unique" if constraint_type == "unique" else "exists"
        constraint_name = _validate_schema_object_name(
            name or f"{label.lower()}_{property_name}_{suffix}"
        )
        if constraint_type == "unique":
            requirement = f"n.{property_name} IS UNIQUE"
        elif constraint_type == "exists":
            requirement = f"n.{property_name} IS NOT NULL"
        else:
            raise ValueError(f"不支持的约束类型: {constraint_type}")

        query = (
            f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE {requirement}"
        )
        self.execute_write(query)
        logger.info("Schema 约束已就绪: %s", constraint_name)
        return True

    def create_index(
        self,
        label: str,
        property_name: str,
        name: str = None,
    ) -> bool:
        """
        创建索引
        
        Args:
            label: 节点标签
            property_name: 属性名
        
        Returns:
            是否成功
        """
        label = validate_node_label(label)
        property_name = validate_property_name(property_name)
        index_name = _validate_schema_object_name(
            name or f"{label.lower()}_{property_name}_idx"
        )
        query = (
            f"CREATE RANGE INDEX {index_name} IF NOT EXISTS "
            f"FOR (n:{label}) ON (n.{property_name})"
        )
        self.execute_write(query)
        logger.info("Schema 索引已就绪: %s", index_name)
        return True

    def drop_constraint(
        self,
        label: str,
        property_name: str,
        name: str = None,
    ) -> bool:
        """
        删除约束
        
        Args:
            label: 节点标签
            property_name: 属性名
        
        Returns:
            是否成功
        """
        label = validate_node_label(label)
        property_name = validate_property_name(property_name)
        constraint_name = _validate_schema_object_name(
            name or f"{label.lower()}_{property_name}_unique"
        )
        self.execute_write(f"DROP CONSTRAINT {constraint_name} IF EXISTS")
        logger.info("Schema 约束已删除: %s", constraint_name)
        return True

    def drop_index(
        self,
        label: str,
        property_name: str,
        name: str = None,
    ) -> bool:
        """
        删除索引
        
        Args:
            label: 节点标签
            property_name: 属性名
        
        Returns:
            是否成功
        """
        label = validate_node_label(label)
        property_name = validate_property_name(property_name)
        index_name = _validate_schema_object_name(
            name or f"{label.lower()}_{property_name}_idx"
        )
        self.execute_write(f"DROP INDEX {index_name} IF EXISTS")
        logger.info("Schema 索引已删除: %s", index_name)
        return True
    
    # ============ 数据库信息 ============
    
    def get_database_info(self) -> Dict[str, Any]:
        """
        获取数据库信息
        
        Returns:
            数据库信息字典
        """
        query = """
        CALL db.info()
        """
        result = self.execute_query(query)
        return result[0] if result else {}
    
    def get_schema(self) -> Dict[str, List]:
        """
        获取数据库Schema
        
        Returns:
            Schema信息
        """
        query = """
        CALL db.schema.visualization()
        """
        return self.execute_query(query)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取数据库统计信息
        
        Returns:
            统计信息
        """
        # 节点统计
        node_query = """
        MATCH (n)
        RETURN labels(n)[0] as label, count(*) as count
        """
        nodes = self.execute_query(node_query)
        
        # 关系统计
        rel_query = """
        MATCH ()-[r]->()
        RETURN type(r) as type, count(*) as count
        """
        rels = self.execute_query(rel_query)
        
        # 总计
        total_nodes = sum(n['count'] for n in nodes)
        total_rels = sum(r['count'] for r in rels)
        
        return {
            "total_nodes": total_nodes,
            "total_relationships": total_rels,
            "nodes_by_label": nodes,
            "relationships_by_type": rels
        }
    
    def clear_database(self) -> bool:
        """
        清空数据库
        
        Returns:
            是否成功
        """
        query = """
        MATCH (n)
        DETACH DELETE n
        """
        return self.execute_write(query)


if __name__ == "__main__":
    # 测试连接
    connector = Neo4jConnector()
    
    # 获取数据库信息
    info = connector.get_database_info()
    print("数据库信息:", info)
    
    # 获取统计信息
    stats = connector.get_statistics()
    print("统计信息:", stats)
    
    connector.close()
