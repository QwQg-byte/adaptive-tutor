import { describe, expect, it } from 'vitest'
import { normalizeNodeTags } from './nodeTags'

describe('normalizeNodeTags', () => {
  it('parses serialized Neo4j arrays instead of iterating characters', () => {
    expect(normalizeNodeTags({
      tags: '["ADT实现","抽象数据类型","编程实现"]'
    })).toEqual(['ADT实现', '抽象数据类型', '编程实现'])
  })

  it('filters empty tags and derives a readable section fallback', () => {
    expect(normalizeNodeTags({
      name: '串匹配',
      tags: '[]',
      section: '4.3 串的模式匹配算法'
    })).toEqual(['串的模式匹配算法'])
  })

  it('supports plain delimited strings and removes duplicates', () => {
    expect(normalizeNodeTags({ tags: '数据结构, 数据结构 基础概念' }))
      .toEqual(['数据结构', '基础概念'])
  })
})
