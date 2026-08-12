export const NODE_TYPE_COLORS = Object.freeze({
  KnowledgeNode: '#409eff',
  Chapter: '#67c23a',
  Question: '#f56c6c',
  NodeType: '#e6a23c',
  Category: '#14b8a6',
  Difficulty: '#d97706',
  '核心抽象': '#5470c6',
  '核心实体': '#91cc75',
  '关键事件': '#fac858'
})

export const NODE_TYPE_LABELS = Object.freeze({
  KnowledgeNode: '知识节点',
  Chapter: '章节',
  Question: '题目',
  NodeType: '节点类型',
  Category: '题目分类',
  Difficulty: '题目难度',
  '核心抽象': '核心抽象',
  '核心实体': '核心实体',
  '关键事件': '关键事件'
})

export const DIFFICULTY_LEVEL_ORDER = Object.freeze(['简单', '中等', '困难', '星耀'])

export const DIFFICULTY_LEVEL_COLORS = Object.freeze({
  简单: '#67c23a',
  中等: '#e6a23c',
  困难: '#f56c6c',
  星耀: '#9c27b0'
})

export const PREFERRED_NODE_TYPE_ORDER = Object.freeze([
  'KnowledgeNode',
  'Chapter',
  'Question',
  'NodeType',
  'Category',
  'Difficulty'
])

export const KNOWLEDGE_SUBTYPE_TYPES = Object.freeze(['核心抽象', '核心实体', '关键事件'])

const NODE_TYPE_TAG_TYPES = Object.freeze({
  KnowledgeNode: 'primary',
  '知识节点': 'primary',
  '知识点': 'primary',
  Chapter: 'success',
  '章节': 'success',
  Question: 'warning',
  '题目': 'warning',
  NodeType: 'info',
  Category: 'success',
  Difficulty: 'warning',
  '核心抽象': 'primary',
  '核心实体': 'success',
  '关键事件': 'warning'
})

export function getNodeTypeColor(type, fallback = '#409eff') {
  return NODE_TYPE_COLORS[type] || fallback
}

export function getNodeTypeLabel(type, fallback = type || '未知类型') {
  return NODE_TYPE_LABELS[type] || fallback
}

export function getNodeTypeTagType(type) {
  return NODE_TYPE_TAG_TYPES[type] || 'info'
}
