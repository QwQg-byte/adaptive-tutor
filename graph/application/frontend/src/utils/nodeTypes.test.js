import { describe, expect, it } from 'vitest'

import {
  DIFFICULTY_LEVEL_COLORS,
  DIFFICULTY_LEVEL_ORDER,
  KNOWLEDGE_SUBTYPE_TYPES,
  NODE_TYPE_COLORS,
  PREFERRED_NODE_TYPE_ORDER,
  getNodeTypeColor,
  getNodeTypeLabel,
  getNodeTypeTagType
} from './nodeTypes'

describe('node type presentation', () => {
  it('keeps graph colors and labels in one mapping', () => {
    expect(getNodeTypeColor('KnowledgeNode')).toBe('#409eff')
    expect(getNodeTypeLabel('Chapter')).toBe('章节')
    expect(getNodeTypeTagType('Question')).toBe('warning')
  })

  it('uses safe fallbacks for unknown types', () => {
    expect(getNodeTypeColor('Custom', '#123456')).toBe('#123456')
    expect(getNodeTypeLabel('Custom')).toBe('Custom')
    expect(getNodeTypeTagType('Custom')).toBe('info')
  })

  it('exports the graph ordering and knowledge subtypes', () => {
    expect(PREFERRED_NODE_TYPE_ORDER[0]).toBe('KnowledgeNode')
    expect(KNOWLEDGE_SUBTYPE_TYPES).toEqual(['核心抽象', '核心实体', '关键事件'])
    expect(NODE_TYPE_COLORS['核心实体']).toBe('#91cc75')
  })

  it('keeps all four algorithm difficulty levels in a stable order', () => {
    expect(DIFFICULTY_LEVEL_ORDER).toEqual(['简单', '中等', '困难', '星耀'])
    expect(DIFFICULTY_LEVEL_COLORS['星耀']).toBe('#9c27b0')
  })
})
