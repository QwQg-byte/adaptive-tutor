import { describe, expect, it } from 'vitest'

import { buildLearningDashboard, getLearningStatus, getMasteryState } from './learningDashboard'

const knowledgePoints = [
  { id: 'NODE_1', name: '线性表', chapter_id: 1 },
  { id: 'NODE_2', name: '栈', chapter_id: 1 },
  { id: 'NODE_3', name: '树', chapter_id: 2 },
  { id: 'NODE_4', name: '图', chapter_id: 2 }
]

const chapters = [
  { id: 'CHAP_1', order: 1, title: '线性结构' },
  { id: 'CHAP_2', order: 2, title: '非线性结构' }
]

describe('learning dashboard aggregation', () => {
  it('maps the four stored progress states into three visual states', () => {
    expect(getLearningStatus({ status: 'mastered', mastery: 100 })).toBe('mastered')
    expect(getLearningStatus({ status: 'completed', mastery: 80 })).toBe('in_progress')
    expect(getLearningStatus({ status: 'in_progress', mastery: 20 })).toBe('in_progress')
    expect(getLearningStatus({ status: 'not_started', mastery: 0 })).toBe('not_started')
    expect(getLearningStatus(null, { updated_at: '2026-07-24T00:00:00Z' })).toBe('mastered')
  })

  it('keeps the five mastery evidence states distinct for graph overlays', () => {
    expect(getMasteryState({ mastery_state: 'assessed_mastery' })).toBe('assessed_mastery')
    expect(getMasteryState({ mastery_state: 'self_reported_mastery' })).toBe('self_reported_mastery')
    expect(getMasteryState({ mastery_state: 'soft_confidence' })).toBe('soft_confidence')
    expect(getMasteryState({ mastery_state: 'weak' })).toBe('weak')
    expect(getMasteryState(null)).toBe('untested')
  })

  it('builds consistent overall, chapter, mistake and recent statistics', () => {
    const dashboard = buildLearningDashboard(knowledgePoints, chapters, {
      mastered: { NODE_1: { updated_at: '2026-07-22T00:00:00Z' } },
      progress: {
        NODE_1: { status: 'mastered', mastery: 100, updated_at: '2026-07-22T00:00:00Z' },
        NODE_2: { status: 'completed', mastery: 80, last_seen_at: '2026-07-24T01:00:00Z' }
      },
      mistakes: {
        Q1: { unresolved: true, wrong_count: 2 },
        Q2: { unresolved: false, wrong_count: 1 }
      }
    })

    expect(dashboard.summary).toEqual({
      total: 4,
      mastered: 1,
      in_progress: 1,
      not_started: 2,
      mastery_percent: 45
    })
    expect(dashboard.chapter_progress[0]).toMatchObject({
      name: '线性结构',
      total: 2,
      mastered: 1,
      in_progress: 1,
      mastery_percent: 90
    })
    expect(dashboard.mistake_summary).toEqual({ total: 2, unresolved: 1, resolved: 1, wrong_attempts: 3 })
    expect(dashboard.recent.map(node => node.id)).toEqual(['NODE_2', 'NODE_1'])
    expect(dashboard.recommendation).toMatchObject({ id: 'NODE_2', status: 'in_progress' })
  })

  it('recommends an unstarted node and handles a fully mastered catalog', () => {
    expect(buildLearningDashboard(knowledgePoints.slice(0, 1), chapters, {}).recommendation)
      .toMatchObject({ id: 'NODE_1', status: 'not_started' })

    const completed = buildLearningDashboard(knowledgePoints.slice(0, 1), chapters, {
      mastered: { NODE_1: {} },
      progress: { NODE_1: { status: 'mastered', mastery: 100 } }
    })
    expect(completed.recommendation).toBeNull()
  })
})
