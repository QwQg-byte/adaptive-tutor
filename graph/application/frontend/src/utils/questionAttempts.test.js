import { describe, expect, it, vi } from 'vitest'

const recordQuestionAttempt = vi.hoisted(() => vi.fn(() => Promise.resolve(null)))
vi.mock('@/stores/progress', () => ({ recordQuestionAttempt }))

import { recordQuestionResult } from './questionAttempts'


describe('question attempt progress wiring', () => {
  it('leaves knowledge attribution to the server', async () => {
    const knowledgePoints = [
      { node_id: 'NODE_1' },
      { id: 'NODE_2' }
    ]

    await recordQuestionResult('Q100', knowledgePoints, false)

    expect(recordQuestionAttempt).toHaveBeenCalledWith('Q100', { correct: false })
  })
})
