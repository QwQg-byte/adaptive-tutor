import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./index', () => ({
  default: vi.fn(config => Promise.resolve(config))
}))

import request from './index'
import { getGraphFragment, getKnowledgePointPage, getNodeNeighbors } from './graph'
import { generatePlan } from './path'
import { getSearchSuggestions, searchByKeyword } from './search'


describe('API request mappings', () => {
  beforeEach(() => {
    request.mockClear()
  })

  it('sends bounded graph fragments and relationship filters in the body', async () => {
    await getGraphFragment(['NODE_1', 'NODE_2'], ['PREREQUISITE'])

    expect(request).toHaveBeenCalledWith({
      url: '/graph/nodes/fragment',
      method: 'post',
      data: {
        node_ids: ['NODE_1', 'NODE_2'],
        relationship_types: ['PREREQUISITE']
      }
    })
  })

  it('encodes neighbor identifiers and omits an empty relationship filter', async () => {
    await getNodeNeighbors('节点/一', 20)

    expect(request).toHaveBeenCalledWith({
      url: '/graph/node/%E8%8A%82%E7%82%B9%2F%E4%B8%80/neighbors',
      method: 'get',
      params: { limit: 20, relationship_types: null }
    })
  })

  it('forwards AbortSignal for pageable knowledge and search requests', async () => {
    const controller = new AbortController()
    await getKnowledgePointPage({ page: 2 }, controller.signal)
    await searchByKeyword({ keyword: '动态规划' }, controller.signal)
    await getSearchSuggestions({ keyword: '动态' }, controller.signal)

    expect(request.mock.calls[0][0].signal).toBe(controller.signal)
    expect(request.mock.calls[1][0].signal).toBe(controller.signal)
    expect(request.mock.calls[2][0].signal).toBe(controller.signal)
  })

  it('passes phase 5 plan state without renaming API fields', async () => {
    const data = {
      target: 'NODE_1',
      mastered: ['NODE_2'],
      completed: ['NODE_3'],
      difficulty_preference: 'challenge'
    }
    await generatePlan(data)

    expect(request).toHaveBeenCalledWith({
      url: '/path/plan',
      method: 'post',
      data
    })
  })
})
