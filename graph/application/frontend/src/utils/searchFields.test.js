import { describe, expect, it } from 'vitest'
import { getSearchPropertyLabel } from './searchFields'

describe('getSearchPropertyLabel', () => {
  it('maps knowledge and question fields to Chinese labels', () => {
    expect(getSearchPropertyLabel('node_id')).toBe('节点编号')
    expect(getSearchPropertyLabel('learning_tips')).toBe('学习建议')
    expect(getSearchPropertyLabel('pass_rate')).toBe('通过率')
    expect(getSearchPropertyLabel('source')).toBe('来源')
  })

  it('keeps unknown extension fields readable', () => {
    expect(getSearchPropertyLabel('custom_field')).toBe('custom_field')
  })
})
