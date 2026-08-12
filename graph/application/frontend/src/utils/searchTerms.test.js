import { describe, expect, it } from 'vitest'

import { normalizeSearchTerm, resolveCanonicalGraphTarget } from './searchTerms'

describe('search term aliases', () => {
  it('normalizes the binary-search synonym to one search term', () => {
    expect(normalizeSearchTerm('折半查找')).toBe('二分查找')
    expect(normalizeSearchTerm(' 二分查找 ')).toBe('二分查找')
    expect(normalizeSearchTerm('折半')).toBe('折半')
  })

  it('resolves the legacy synonym node and canonical node to NODE_381', () => {
    for (const target of ['折半查找', '二分查找', '246', 'NODE_246', '381', 'NODE_381']) {
      expect(resolveCanonicalGraphTarget(target)).toBe('NODE_381')
    }
    expect(resolveCanonicalGraphTarget('NODE_100')).toBe('NODE_100')
  })
})
