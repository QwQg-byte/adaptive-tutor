import { describe, expect, it } from 'vitest'
import { collectRetainedGraphIds } from './graphFragments'

describe('collectRetainedGraphIds', () => {
  it('keeps base, retained, and still-expanded graph elements', () => {
    const expansionFragments = new Map([
      ['NODE_A', {
        nodeIds: new Set(['NODE_A', 'NODE_SHARED']),
        edgeIds: new Set(['A-SHARED'])
      }]
    ])

    const result = collectRetainedGraphIds({
      baseNodeIds: new Set(['NODE_BASE']),
      baseEdgeIds: new Set(['BASE-EDGE']),
      retainedNodeIds: new Set(['NODE_PATH', 'NODE_SHARED']),
      retainedEdgeIds: new Set(['PATH-EDGE']),
      expansionFragments
    })

    expect([...result.nodeIds]).toEqual([
      'NODE_BASE',
      'NODE_PATH',
      'NODE_SHARED',
      'NODE_A'
    ])
    expect([...result.edgeIds]).toEqual(['BASE-EDGE', 'PATH-EDGE', 'A-SHARED'])
  })

  it('drops elements owned only by a removed expansion', () => {
    const expansionFragments = new Map([
      ['NODE_B', {
        nodeIds: new Set(['NODE_B', 'NODE_SHARED']),
        edgeIds: new Set(['B-SHARED'])
      }]
    ])

    const result = collectRetainedGraphIds({
      baseNodeIds: ['NODE_BASE', 'NODE_SHARED'],
      baseEdgeIds: ['BASE-SHARED'],
      expansionFragments
    })

    expect(result.nodeIds.has('NODE_A_ONLY')).toBe(false)
    expect(result.edgeIds.has('A-ONLY')).toBe(false)
    expect(result.nodeIds.has('NODE_SHARED')).toBe(true)
    expect(result.edgeIds.has('B-SHARED')).toBe(true)
  })
})
