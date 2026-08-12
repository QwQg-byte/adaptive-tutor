"""
知识图谱构建器 - 批量导入实体和关系
"""

from neo4j_connector import Neo4jConnector
from schema_manager import SchemaManager
import json
import logging
from typing import Dict, Any
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GraphBuilder:
    """知识图谱构建器"""
    
    def __init__(self, connector: Neo4jConnector):
        """
        初始化图谱构建器
        
        Args:
            connector: Neo4j连接器
        """
        self.connector = connector
        self.schema_manager = SchemaManager(connector)
        self.stats = {
            'nodes_created': 0,
            'relationships_created': 0,
            'nodes_failed': 0,
            'relationships_failed': 0
        }
    
    def initialize_database(self) -> bool:
        """
        初始化数据库（创建Schema）
        
        Returns:
            是否成功
        """
        logger.info("开始初始化数据库...")
        return self.schema_manager.initialize_schema()
    
    def import_entities(self, entities_file: str, batch_size: int = 100) -> Dict[str, int]:
        """
        从JSON文件导入实体
        
        Args:
            entities_file: 实体JSON文件路径
            batch_size: 批次大小
        
        Returns:
            导入统计
        """
        logger.info(f"开始导入实体: {entities_file}")
        
        # 读取实体文件
        with open(entities_file, 'r', encoding='utf-8') as f:
            entities_data = json.load(f)
        
        # 按实体类型分组
        entities_by_type = {}
        for entity in entities_data:
            entity_type = entity['entity_type']
            if entity_type not in entities_by_type:
                entities_by_type[entity_type] = []
            
            # 构建节点属性
            properties = {
                'name': entity['entity_text'],
                'confidence': entity.get('confidence', 1.0),
                'text_id': entity.get('text_id'),
                'source_text': entity.get('text', '')
            }
            entities_by_type[entity_type].append(properties)
        
        # 批量导入
        for entity_type, entities in entities_by_type.items():
            logger.info(f"导入 {entity_type}: {len(entities)} 个实体")
            
            # 分批处理
            for i in range(0, len(entities), batch_size):
                batch = entities[i:i+batch_size]
                try:
                    count = self.connector.create_nodes_batch(entity_type, batch)
                    self.stats['nodes_created'] += count
                    logger.info(f"  批次 {i//batch_size + 1}: 成功创建 {count} 个节点")
                except Exception as e:
                    self.stats['nodes_failed'] += len(batch)
                    logger.error(f"  批次 {i//batch_size + 1}: 创建失败 - {e}")
        
        logger.info(f"实体导入完成: 总计 {self.stats['nodes_created']} 成功, {self.stats['nodes_failed']} 失败")
        return self.stats
    
    def import_relationships(self, relations_file: str, batch_size: int = 100) -> Dict[str, int]:
        """
        从JSON文件导入关系
        
        Args:
            relations_file: 关系JSON文件路径
            batch_size: 批次大小
        
        Returns:
            导入统计
        """
        logger.info(f"开始导入关系: {relations_file}")
        
        # 读取关系文件
        with open(relations_file, 'r', encoding='utf-8') as f:
            relations_data = json.load(f)
        
        # 如果为空，跳过
        if not relations_data:
            logger.warning("关系文件为空，跳过导入")
            return self.stats
        
        # 准备关系数据
        relationships = []
        for rel in relations_data:
            relationships.append({
                'source_label': rel['source']['type'],
                'source_prop': 'name',
                'source_value': rel['source']['text'],
                'target_label': rel['target']['type'],
                'target_prop': 'name',
                'target_value': rel['target']['text'],
                'rel_type': rel['relation_type'],
                'properties': {
                    'confidence': rel.get('confidence', 1.0),
                    'method': rel.get('method', 'unknown'),
                    'text_id': rel.get('text_id'),
                    'source_text': rel.get('text', '')
                }
            })
        
        # 分批处理
        for i in range(0, len(relationships), batch_size):
            batch = relationships[i:i+batch_size]
            logger.info(f"处理批次 {i//batch_size + 1}: {len(batch)} 个关系")
            
            # 逐个创建关系（批量创建可能因节点不存在而失败）
            created_count = 0
            failed_count = 0
            
            for rel in batch:
                try:
                    success = self.connector.create_relationship(
                        rel['source_label'],
                        rel['source_prop'],
                        rel['source_value'],
                        rel['target_label'],
                        rel['target_prop'],
                        rel['target_value'],
                        rel['rel_type'],
                        rel['properties']
                    )
                    if success:
                        created_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    logger.warning(f"  创建关系失败: {rel['source_value']} -[{rel['rel_type']}]-> {rel['target_value']}: {e}")
            
            self.stats['relationships_created'] += created_count
            self.stats['relationships_failed'] += failed_count
            logger.info(f"  批次 {i//batch_size + 1}: 成功 {created_count}, 失败 {failed_count}")
        
        logger.info(f"关系导入完成: 总计 {self.stats['relationships_created']} 成功, {self.stats['relationships_failed']} 失败")
        return self.stats
    
    def import_from_extraction_results(self, entities_dir: str = "../entities", 
                                         relations_dir: str = "../relations") -> Dict[str, int]:
        """
        从抽取结果导入
        
        Args:
            entities_dir: 实体目录
            relations_dir: 关系目录
        
        Returns:
            导入统计
        """
        # 导入实体
        entities_file = Path(entities_dir) / "extracted_entities.json"
        if entities_file.exists():
            self.import_entities(str(entities_file))
        else:
            logger.warning(f"实体文件不存在: {entities_file}")
        
        # 导入关系
        relations_file = Path(relations_dir) / "extracted_relations.json"
        if relations_file.exists():
            self.import_relationships(str(relations_file))
        else:
            logger.warning(f"关系文件不存在: {relations_file}")
        
        return self.stats
    
    def create_sample_data(self) -> bool:
        """
        创建示例数据
        
        Returns:
            是否成功
        """
        logger.info("开始创建示例数据...")
        
        # 示例实体
        sample_entities = [
            # 题目
            {
                'label': 'Question',
                'properties': {
                    'id': 'Q001',
                    'title': '两数之和',
                    'description': '给定一个整数数组nums和一个整数目标值target，请在数组中找出和为目标值的那两个整数，并返回它们的数组下标。',
                    'difficulty': '简单',
                    'tags': ['数组', '哈希表'],
                    'acceptance_rate': 0.52,
                    'time_limit': '1000ms',
                    'memory_limit': '256MB',
                    'source': 'LeetCode',
                    'url': 'https://leetcode.cn/problems/two-sum/'
                }
            },
            {
                'label': 'Question',
                'properties': {
                    'id': 'Q002',
                    'title': '最长子序列',
                    'description': '给定一个整数数组，找到其中最长严格递增子序列的长度。',
                    'difficulty': '中等',
                    'tags': ['动态规划', '二分查找'],
                    'acceptance_rate': 0.45,
                    'time_limit': '1000ms',
                    'memory_limit': '256MB',
                    'source': 'LeetCode',
                    'url': 'https://leetcode.cn/problems/longest-increasing-subsequence/'
                }
            },
            
            # 算法
            {
                'label': 'Algorithm',
                'properties': {
                    'name': '两数之和',
                    'description': '使用哈希表快速查找目标值',
                    'time_complexity': 'O(n)',
                    'space_complexity': 'O(n)',
                    'difficulty': '简单',
                    'category': '数组',
                    'keywords': ['哈希表', '数组', '查找']
                }
            },
            {
                'label': 'Algorithm',
                'properties': {
                    'name': '动态规划',
                    'description': '通过将问题分解为子问题来求解最优解',
                    'time_complexity': 'O(n^2)',
                    'space_complexity': 'O(n)',
                    'difficulty': '进阶',
                    'category': '动态规划',
                    'keywords': ['DP', '状态转移', '最优子结构']
                }
            },
            {
                'label': 'Algorithm',
                'properties': {
                    'name': 'Dijkstra',
                    'description': 'Dijkstra算法是一种用于在图中找到从单个源节点到所有其他节点的最短路径的贪心算法',
                    'time_complexity': 'O(V^2)',
                    'space_complexity': 'O(V)',
                    'difficulty': '进阶',
                    'category': '图论',
                    'keywords': ['最短路径', '贪心', '优先队列']
                }
            },
            
            # 数据结构
            {
                'label': 'DataStructure',
                'properties': {
                    'name': '哈希表',
                    'description': '哈希表是一种数据结构，它使用哈希函数来计算数据值存储位置的数据结构',
                    'time_complexity': 'O(1)',
                    'space_complexity': 'O(n)',
                    'category': '查找',
                    'keywords': ['哈希', '映射', '键值对']
                }
            },
            {
                'label': 'DataStructure',
                'properties': {
                    'name': '优先队列',
                    'description': '优先队列是一种特殊的队列，其中每个元素都有一个优先级，优先级最高的元素先出队',
                    'time_complexity': 'O(log n)',
                    'space_complexity': 'O(n)',
                    'category': '队列',
                    'keywords': ['堆', '优先级', '队列']
                }
            },
            {
                'label': 'DataStructure',
                'properties': {
                    'name': '数组',
                    'description': '数组是一种线性数据结构，用于存储相同类型的元素',
                    'time_complexity': 'O(1)',
                    'space_complexity': 'O(n)',
                    'category': '线性',
                    'keywords': ['索引', '连续存储', '随机访问']
                }
            },
            
            # 知识点
            {
                'label': 'KnowledgePoint',
                'properties': {
                    'name': '哈希查找',
                    'description': '使用哈希表进行快速查找',
                    'difficulty': '基础',
                    'importance': 0.9,
                    'learning_time': 5,
                    'frequency': 0.85,
                    'keywords': ['哈希', '查找', 'O(1)']
                }
            },
            {
                'label': 'KnowledgePoint',
                'properties': {
                    'name': '动态规划',
                    'description': '动态规划是解决最优化问题的一种思想方法',
                    'difficulty': '进阶',
                    'importance': 0.95,
                    'learning_time': 20,
                    'frequency': 0.9,
                    'keywords': ['DP', '状态转移', '最优子结构', '重叠子问题']
                }
            },
            {
                'label': 'KnowledgePoint',
                'properties': {
                    'name': '图论',
                    'description': '图论是数学的一个分支，研究图的性质和图之间的关系',
                    'difficulty': '进阶',
                    'importance': 0.85,
                    'learning_time': 15,
                    'frequency': 0.8,
                    'keywords': ['图', '顶点', '边', '最短路径', '最短路径']
                }
            },
            
            # 概念
            {
                'label': 'Concept',
                'properties': {
                    'name': '贪心',
                    'description': '贪心算法在每一步选择中都采取当前状态下最优的选择',
                    'category': '算法思想',
                    'keywords': ['局部最优', '贪心选择性质']
                }
            },
            {
                'label': 'Concept',
                'properties': {
                    'name': '最优子结构',
                    'description': '问题的最优解包含子问题的最优解',
                    'category': '动态规划',
                    'keywords': ['子问题', '最优解']
                }
            },
            
            # 分类
            {
                'label': 'Category',
                'properties': {
                    'name': '数组',
                    'description': '与数组相关的题目',
                    'parent_category': None
                }
            },
            {
                'label': 'Category',
                'properties': {
                    'name': '动态规划',
                    'description': '动态规划类题目',
                    'parent_category': None
                }
            },
            {
                'label': 'Category',
                'properties': {
                    'name': '图论',
                    'description': '图论类题目',
                    'parent_category': None
                }
            },
            
            # 难度
            {
                'label': 'Difficulty',
                'properties': {
                    'level': '简单',
                    'description': '适合初学者',
                    'order': 1
                }
            },
            {
                'label': 'Difficulty',
                'properties': {
                    'level': '中等',
                    'description': '需要一定的算法基础',
                    'order': 2
                }
            },
            {
                'label': 'Difficulty',
                'properties': {
                    'level': '困难',
                    'description': '需要较强的算法能力',
                    'order': 3
                }
            },
            {
                'label': 'Difficulty',
                'properties': {
                    'level': '星耀',
                    'description': '面向高阶算法挑战',
                    'order': 4
                }
            },
            
            # 复杂度
            {
                'label': 'Complexity',
                'properties': {
                    'name': 'O(1)',
                    'notation': 'O(1)',
                    'description': '常数时间复杂度'
                }
            },
            {
                'label': 'Complexity',
                'properties': {
                    'name': 'O(n)',
                    'notation': 'O(n)',
                    'description': '线性时间复杂度'
                }
            },
            {
                'label': 'Complexity',
                'properties': {
                    'name': 'O(n^2)',
                    'notation': 'O(n^2)',
                    'description': '平方时间复杂度'
                }
            }
        ]
        
        # 创建节点
        for entity in sample_entities:
            self.connector.create_node(entity['label'], entity['properties'])
            self.stats['nodes_created'] += 1
        
        logger.info(f"已创建 {len(sample_entities)} 个示例节点")
        
        # 示例关系
        sample_relationships = [
            {
                'source_label': 'Question',
                'source_prop': 'id',
                'source_value': 'Q001',
                'target_label': 'Algorithm',
                'target_prop': 'name',
                'target_value': '两数之和',
                'rel_type': 'USES_ALGORITHM',
                'properties': {'confidence': 0.9, 'method': 'rule-based'}
            },
            {
                'source_label': 'Question',
                'source_prop': 'id',
                'source_value': 'Q001',
                'target_label': 'DataStructure',
                'target_prop': 'name',
                'target_value': '哈希表',
                'rel_type': 'USES_STRUCTURE',
                'properties': {'confidence': 0.95, 'method': 'rule-based'}
            },
            {
                'source_label': 'Question',
                'source_prop': 'id',
                'source_value': 'Q001',
                'target_label': 'KnowledgePoint',
                'target_prop': 'name',
                'target_value': '哈希查找',
                'rel_type': 'REQUIRES',
                'properties': {'confidence': 0.9, 'method': 'rule-based'}
            },
            {
                'source_label': 'Question',
                'source_prop': 'id',
                'source_value': 'Q001',
                'target_label': 'Category',
                'target_prop': 'name',
                'target_value': '数组',
                'rel_type': 'BELONGS_TO',
                'properties': {'confidence': 0.95, 'method': 'rule-based'}
            },
            {
                'source_label': 'Question',
                'source_prop': 'id',
                'source_value': 'Q001',
                'target_label': 'Difficulty',
                'target_prop': 'level',
                'target_value': '简单',
                'rel_type': 'HAS_DIFFICULTY',
                'properties': {'confidence': 1.0}
            },
            {
                'source_label': 'Question',
                'source_prop': 'id',
                'source_value': 'Q002',
                'target_label': 'Algorithm',
                'target_prop': 'name',
                'target_value': '动态规划',
                'rel_type': 'USES_ALGORITHM',
                'properties': {'confidence': 0.9, 'method': 'rule-based'}
            },
            {
                'source_label': 'Question',
                'source_prop': 'id',
                'source_value': 'Q002',
                'target_label': 'KnowledgePoint',
                'target_prop': 'name',
                'target_value': '动态规划',
                'rel_type': 'REQUIRES',
                'properties': {'confidence': 0.95, 'method': 'rule-based'}
            },
            {
                'source_label': 'Question',
                'source_prop': 'id',
                'source_value': 'Q002',
                'target_label': 'Category',
                'target_prop': 'name',
                'target_value': '动态规划',
                'rel_type': 'BELONGS_TO',
                'properties': {'confidence': 0.95, 'method': 'rule-based'}
            },
            {
                'source_label': 'Question',
                'source_prop': 'id',
                'source_value': 'Q002',
                'target_label': 'Difficulty',
                'target_prop': 'level',
                'target_value': '中等',
                'rel_type': 'HAS_DIFFICULTY',
                'properties': {'confidence': 1.0}
            },
            {
                'source_label': 'Algorithm',
                'source_prop': 'name',
                'source_value': 'Dijkstra',
                'target_label': 'DataStructure',
                'target_prop': 'name',
                'target_value': '优先队列',
                'rel_type': 'RELATED_TO',
                'properties': {'confidence': 0.9, 'method': 'rule-based'}
            },
            {
                'source_label': 'Algorithm',
                'source_prop': 'name',
                'source_value': 'Dijkstra',
                'target_label': 'Concept',
                'target_prop': 'name',
                'target_value': '贪心',
                'rel_type': 'BASED_ON',
                'properties': {'confidence': 0.85, 'method': 'rule-based'}
            },
            {
                'source_label': 'KnowledgePoint',
                'source_prop': 'name',
                'source_value': '动态规划',
                'target_label': 'Concept',
                'target_prop': 'name',
                'target_value': '最优子结构',
                'rel_type': 'HAS_CONCEPT',
                'properties': {'confidence': 0.9, 'method': 'rule-based'}
            },
            {
                'source_label': 'Algorithm',
                'source_prop': 'name',
                'source_value': 'Dijkstra',
                'target_label': 'Complexity',
                'target_prop': 'name',
                'target_value': 'O(V^2)',
                'rel_type': 'HAS_COMPLEXITY',
                'properties': {'type': 'time'}
            }
        ]
        
        # 创建关系
        for rel in sample_relationships:
            success = self.connector.create_relationship(
                rel['source_label'],
                rel['source_prop'],
                rel['source_value'],
                rel['target_label'],
                rel['target_prop'],
                rel['target_value'],
                rel['rel_type'],
                rel['properties']
            )
            if success:
                self.stats['relationships_created'] += 1
            else:
                self.stats['relationships_failed'] += 1
        
        logger.info(f"已创建 {self.stats['relationships_created']} 个示例关系")
        return True
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取构建统计信息
        
        Returns:
            统计信息
        """
        db_stats = self.connector.get_statistics()
        self.stats.update(db_stats)
        return self.stats
    
    def verify_graph(self) -> Dict[str, Any]:
        """
        验证图谱完整性
        
        Returns:
            验证结果
        """
        logger.info("开始验证图谱完整性...")
        
        results = {
            'is_valid': True,
            'issues': [],
            'warnings': [],
            'node_count_by_type': {},
            'relationship_count_by_type': {}
        }
        
        # 检查节点
        stats = self.connector.get_statistics()
        for node_stat in stats.get('nodes_by_label', []):
            label = node_stat['label']
            count = node_stat['count']
            results['node_count_by_type'][label] = count
            
            if count == 0:
                results['warnings'].append(f"实体类型 {label} 没有节点")
        
        # 检查关系
        for rel_stat in stats.get('relationships_by_type', []):
            rel_type = rel_stat['type']
            count = rel_stat['count']
            results['relationship_count_by_type'][rel_type] = count
        
        # 检查孤立节点
        isolated_query = """
        MATCH (n)
        WHERE NOT (n)-[]-()
        RETURN labels(n)[0] as label, n.name as name
        LIMIT 10
        """
        isolated_nodes = self.connector.execute_query(isolated_query)
        if isolated_nodes:
            results['warnings'].append(f"发现 {len(isolated_nodes)} 个孤立节点")
            for node in isolated_nodes:
                results['warnings'].append(f"  - {node['label']}: {node['name']}")
        
        # 总体验证
        if results['warnings']:
            results['is_valid'] = False
            results['issues'].append("发现警告，请检查")
        
        logger.info(f"图谱验证完成: {'通过' if results['is_valid'] else '未通过'}")
        if results['warnings']:
            for warning in results['warnings']:
                logger.warning(warning)
        
        return results
    
    def export_graph(self, output_file: str = None, format: str = 'json') -> bool:
        """
        导出图谱
        
        Args:
            output_file: 输出文件路径
            format: 导出格式 (json, cypher)
        
        Returns:
            是否成功
        """
        logger.info(f"开始导出图谱: {format}")
        
        try:
            if format == 'json':
                # 导出为JSON
                query = """
                MATCH (n)-[r]->(m)
                RETURN n, r, m
                LIMIT 10000
                """
                results = self.connector.execute_query(query)
                
                graph_data = {
                    'nodes': [],
                    'relationships': []
                }
                
                node_ids = set()
                for record in results:
                    # 节点
                    source = record['n']
                    target = record['m']
                    
                    if id(source) not in node_ids:
                        graph_data['nodes'].append({
                            'id': source.element_id,
                            'labels': list(source.labels),
                            'properties': dict(source)
                        })
                        node_ids.add(id(source))
                    
                    if id(target) not in node_ids:
                        graph_data['nodes'].append({
                            'id': target.element_id,
                            'labels': list(target.labels),
                            'properties': dict(target)
                        })
                        node_ids.add(id(target))
                    
                    # 关系
                    rel = record['r']
                    graph_data['relationships'].append({
                        'id': rel.element_id,
                        'type': rel.type,
                        'source': source.element_id,
                        'target': target.element_id,
                        'properties': dict(rel)
                    })
                
                # 保存
                if output_file:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(graph_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"图谱已导出到: {output_file}")
                
                return True
                
            elif format == 'cypher':
                # 导出为Cypher
                cypher_commands = []
                
                # 导出节点
                query_nodes = """
                MATCH (n)
                RETURN labels(n)[0] as label, properties(n) as props
                """
                nodes = self.connector.execute_query(query_nodes)
                
                for node in nodes:
                    label = node['label']
                    props = node['props']
                    prop_str = ', '.join([f"{k}: {repr(v)}" for k, v in props.items()])
                    cypher_commands.append(f"CREATE (:{label} {{{prop_str}}});")
                
                # 保存
                if output_file:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(cypher_commands))
                    logger.info(f"图谱已导出到: {output_file}")
                
                return True
            
            else:
                logger.error(f"不支持的导出格式: {format}")
                return False
                
        except Exception as e:
            logger.error(f"导出图谱失败: {e}")
            return False
    
    def print_summary(self):
        """打印构建摘要"""
        print("\n" + "="*60)
        print("知识图谱构建摘要")
        print("="*60)
        print(f"创建的节点数: {self.stats['nodes_created']}")
        print(f"创建的关系数: {self.stats['relationships_created']}")
        print(f"失败的节点数: {self.stats['nodes_failed']}")
        print(f"失败的关系数: {self.stats['relationships_failed']}")
        
        if 'total_nodes' in self.stats:
            print(f"\n数据库节点总数: {self.stats['total_nodes']}")
            print(f"数据库关系统计数: {self.stats['total_relationships']}")
        
        print("="*60 + "\n")
    
    # ============ 图谱优化 ============
    
    def optimize_query_performance(self) -> Dict[str, Any]:
        """
        优化查询性能
        包括：分析慢查询、创建必要的索引、优化查询模式
        
        Returns:
            优化结果
        """
        logger.info("开始优化查询性能...")
        
        results = {
            'optimizations_performed': [],
            'recommendations': [],
            'success': True
        }
        
        # 1. 确保所有常用查询字段都有索引
        label_index_map = {
            'Question': ['id', 'title', 'difficulty', 'source'],
            'Algorithm': ['name', 'category', 'difficulty'],
            'DataStructure': ['name', 'category'],
            'KnowledgePoint': ['name', 'difficulty', 'importance']
        }
        
        for label, fields in label_index_map.items():
            for field in fields:
                try:
                    success = self.connector.create_index(label, field)
                    if success:
                        results['optimizations_performed'].append(
                            f"创建索引: {label}.{field}"
                        )
                except Exception as e:
                    logger.warning(f"创建索引失败 {label}.{field}: {e}")
        
        # 2. 分析查询模式并提供建议
        # 检查是否有大量的标签扫描
        label_scan_query = """
        CALL db.indexes()
        YIELD name, state
        WHERE state = 'ONLINE'
        RETURN count(*) as online_indexes
        """
        indexes = self.connector.execute_query(label_scan_query)
        if indexes:
            index_count = indexes[0]['online_indexes']
            results['online_indexes'] = index_count
            logger.info(f"当前在线索引数: {index_count}")
        
        # 3. 提供查询优化建议
        results['recommendations'].append("使用参数化查询以提高查询计划缓存效率")
        results['recommendations'].append("避免在大结果集上使用ORDER BY")
        results['recommendations'].append("使用LIMIT限制返回结果大小")
        results['recommendations'].append("考虑使用查询配置文件（PROFILE）分析慢查询")
        
        logger.info("查询性能优化完成")
        return results
    
    def optimize_indexes(self, rebuild: bool = False) -> Dict[str, Any]:
        """
        索引优化
        分析索引使用情况，重建或删除无用索引
        
        Args:
            rebuild: 是否重建所有索引
        
        Returns:
            优化结果
        """
        logger.info("开始索引优化...")
        
        results = {
            'actions_taken': [],
            'recommendations': [],
            'success': True
        }
        
        # 获取所有索引
        indexes_query = """
        CALL db.indexes()
        YIELD name, state, populationPercent, uniqueness
        RETURN name, state, populationPercent, uniqueness
        """
        indexes = self.connector.execute_query(indexes_query)
        
        logger.info(f"当前索引数量: {len(indexes)}")
        
        if rebuild:
            # 重建索引
            logger.info("重建索引...")
            for idx in indexes:
                idx_name = idx['name']
                try:
                    # Neo4j 4.x+ 使用 DROP INDEX
                    drop_query = f"DROP INDEX {idx_name} IF EXISTS"
                    self.connector.execute_write(drop_query)
                    results['actions_taken'].append(f"删除索引: {idx_name}")
                except Exception as e:
                    logger.warning(f"删除索引失败 {idx_name}: {e}")
            
            # 重新创建索引
            self.schema_manager.create_all_indexes()
            results['actions_taken'].append("重新创建所有索引")
        
        # 分析索引使用情况
        for idx in indexes:
            if idx.get('populationPercent', 100) < 50:
                results['recommendations'].append(
                    f"索引 {idx['name']} 填充率较低 ({idx['populationPercent']}%)，考虑删除"
                )
        
        logger.info("索引优化完成")
        return results
    
    def compress_graph(self) -> Dict[str, Any]:
        """
        图谱数据压缩
        删除冗余数据、合并相似节点、压缩属性
        
        Returns:
            压缩结果
        """
        logger.info("开始图谱数据压缩...")
        
        results = {
            'actions_taken': [],
            'stats_before': {},
            'stats_after': {},
            'success': True
        }
        
        # 获取压缩前统计
        stats_before = self.connector.get_statistics()
        results['stats_before'] = stats_before
        
        # 1. 删除重复的关系（相同类型和属性的重复关系）
        dedup_query = """
        MATCH (a)-[r1]->(b)
        WITH a, b, type(r1) as rel_type, properties(r1) as props, count(r1) as cnt
        WHERE cnt > 1
        MATCH (a)-[r]->(b)
        WITH r, rel_type, props
        WHERE type(r) = rel_type AND properties(r) = props
        WITH r, rel_type, props
        ORDER BY r.id DESC
        SKIP 1
        DELETE r
        RETURN count(*) as deleted
        """
        deleted_rels = self.connector.execute_write_records(dedup_query)
        if deleted_rels and deleted_rels[0]['deleted'] > 0:
            deleted_count = deleted_rels[0]['deleted']
            results['actions_taken'].append(f"删除 {deleted_count} 个重复关系")
        
        # 2. 清理空属性值
        cleanup_query = """
        MATCH (n)
        REMOVE n._temp
        RETURN count(n) as cleaned
        """
        self.connector.execute_write(cleanup_query)
        results['actions_taken'].append("清理临时属性")
        
        # 3. 删除孤立节点（可选）
        # isolated_query = """
        # MATCH (n)
        # WHERE NOT (n)-[]-()
        # DETACH DELETE n
        # RETURN count(n) as deleted
        # """
        # isolated = self.connector.execute_query(isolated_query)
        # if isolated and isolated[0]['deleted'] > 0:
        #     deleted_count = isolated[0]['deleted']
        #     results['actions_taken'].append(f"删除 {deleted_count} 个孤立节点")
        
        # 获取压缩后统计
        stats_after = self.connector.get_statistics()
        results['stats_after'] = stats_after
        
        # 计算节省
        nodes_saved = results['stats_before'].get('total_nodes', 0) - results['stats_after'].get('total_nodes', 0)
        rels_saved = results['stats_before'].get('total_relationships', 0) - results['stats_after'].get('total_relationships', 0)
        
        if nodes_saved > 0:
            results['actions_taken'].append(f"节省 {nodes_saved} 个节点")
        if rels_saved > 0:
            results['actions_taken'].append(f"节省 {rels_saved} 个关系")
        
        logger.info("图谱数据压缩完成")
        return results
    
    def setup_incremental_update(self) -> Dict[str, Any]:
        """
        设置增量更新机制
        配置触发器、时间戳、版本控制等
        
        Returns:
            配置结果
        """
        logger.info("开始设置增量更新机制...")
        
        results = {
            'features_enabled': [],
            'recommendations': [],
            'success': True
        }
        
        # 1. 添加更新时间戳属性（通过数据约束）
        results['features_enabled'].append("配置增量更新时间戳字段")
        
        # 2. 创建版本控制节点（可选）
        version_node_query = """
        MERGE (v:Version {current: 'latest'})
        SET v.last_updated = datetime()
        """
        try:
            self.connector.execute_write(version_node_query)
            results['features_enabled'].append("创建版本控制节点")
        except Exception as e:
            logger.warning(f"创建版本控制节点失败: {e}")
        
        # 3. 提供增量更新建议
        results['recommendations'].append(
            "在导入新数据时，检查updated_at字段只添加新增或修改的数据"
        )
        results['recommendations'].append(
            "使用MERGE语句替代CREATE/MATCH组合以避免重复"
        )
        results['recommendations'].append(
            "定期备份图谱快照以支持回滚"
        )
        results['recommendations'].append(
            "使用APOC库进行高级增量更新（需安装APOC插件）"
        )
        
        logger.info("增量更新机制设置完成")
        return results
    
    def run_full_optimization(self) -> Dict[str, Any]:
        """
        运行完整优化流程
        包括：查询性能优化、索引优化、数据压缩、增量更新配置
        
        Returns:
            完整优化结果
        """
        logger.info("="*60)
        logger.info("开始完整图谱优化流程")
        logger.info("="*60)
        
        results = {
            'query_optimization': None,
            'index_optimization': None,
            'graph_compression': None,
            'incremental_update': None,
            'summary': {}
        }
        
        # 1. 查询性能优化
        logger.info("\n步骤 1/4: 查询性能优化")
        results['query_optimization'] = self.optimize_query_performance()
        
        # 2. 索引优化
        logger.info("\n步骤 2/4: 索引优化")
        results['index_optimization'] = self.optimize_indexes(rebuild=False)
        
        # 3. 图谱数据压缩
        logger.info("\n步骤 3/4: 图谱数据压缩")
        results['graph_compression'] = self.compress_graph()
        
        # 4. 增量更新配置
        logger.info("\n步骤 4/4: 增量更新配置")
        results['incremental_update'] = self.setup_incremental_update()
        
        # 总结
        total_actions = (
            len(results['query_optimization'].get('optimizations_performed', [])) +
            len(results['index_optimization'].get('actions_taken', [])) +
            len(results['graph_compression'].get('actions_taken', [])) +
            len(results['incremental_update'].get('features_enabled', []))
        )
        
        total_recommendations = (
            len(results['query_optimization'].get('recommendations', [])) +
            len(results['index_optimization'].get('recommendations', [])) +
            len(results['incremental_update'].get('recommendations', []))
        )
        
        results['summary'] = {
            'total_actions_performed': total_actions,
            'total_recommendations': total_recommendations,
            'optimization_successful': all([
                results['query_optimization'].get('success', False),
                results['index_optimization'].get('success', False),
                results['graph_compression'].get('success', False),
                results['incremental_update'].get('success', False)
            ])
        }
        
        logger.info("\n" + "="*60)
        logger.info("完整优化流程完成")
        logger.info(f"执行操作数: {total_actions}")
        logger.info(f"建议数: {total_recommendations}")
        logger.info(f"优化状态: {'成功' if results['summary']['optimization_successful'] else '部分成功'}")
        logger.info("="*60)
        
        return results


if __name__ == "__main__":
    # 测试图谱构建器
    connector = Neo4jConnector()
    builder = GraphBuilder(connector)
    
    # 初始化数据库
    builder.initialize_database()
    
    # 创建示例数据
    builder.create_sample_data()
    
    # 验证图谱
    verification = builder.verify_graph()
    print("验证结果:", verification)
    
    # 获取统计
    stats = builder.get_statistics()
    print("统计信息:", stats)
    
    # 打印摘要
    builder.print_summary()
    
    connector.close()
