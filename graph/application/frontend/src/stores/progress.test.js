import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getLearnerState: vi.fn(),
  getLearnerMistakes: vi.fn(),
  updateKnowledgeState: vi.fn(),
  updatePlanStep: vi.fn(),
  recordLearnerAttempt: vi.fn(),
  updateMistakeState: vi.fn(),
  importLocalV1: vi.fn(),
  createIdempotencyKey: vi.fn(prefix => `${prefix}:test-key`),
  getStudentId: vi.fn(() => 'student-1'),
  isRevisionConflict: vi.fn(() => false)
}))

vi.mock('@/api/learner', () => api)

import {
  exportLearningState,
  getLearningState,
  getMastered,
  getMistakes,
  getPlanDone,
  importLearningState,
  legacyMigrationPending,
  loadLearningState,
  migrateLegacyLearningState,
  recordQuestionAttempt,
  resetLearningStateCache,
  setMastered,
  togglePlanStep
} from './progress'


function serverState(revision = 3) {
  return {
    student_id: 'student-1',
    revision,
    mastery_nodes: [
      {
        node_id: 'NODE_1',
        node_name: '节点一',
        mastery: 0.8,
        mastery_state: 'assessed_mastery',
        evidence_source: 'practice',
        manual_override: null,
        attempts: 3,
        correct: 3,
        updated_at: 10
      }
    ],
    plan_progress: [
      { target_id: 'TARGET', node_id: 'NODE_2', status: 'completed', completed_at: 9 }
    ],
    open_mistakes: [],
    recent_events: [],
    mistake_summary: { total: 1, open: 1, resolved: 0, wrong_attempts: 2 }
  }
}

function serverMistakes(revision = 3) {
  return {
    revision,
    items: [
      {
        question_id: 'Q1',
        status: 'open',
        wrong_count: 2,
        correct_after_wrong_count: 0,
        primary_node_id: 'NODE_1',
        updated_at: 11
      }
    ]
  }
}

describe('server-backed learning progress cache', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    resetLearningStateCache()
    api.getLearnerState.mockResolvedValue(serverState())
    api.getLearnerMistakes.mockResolvedValue(serverMistakes())
  })

  it('adapts one server revision for mastery, plans and mistakes', async () => {
    await loadLearningState()

    expect(getLearningState()).toMatchObject({ version: 2, revision: 3, loaded: true })
    expect(getMastered()).toEqual(['NODE_1'])
    expect(getPlanDone('TARGET')).toEqual(['NODE_2'])
    expect(getMistakes()[0]).toMatchObject({
      question_id: 'Q1',
      unresolved: true,
      wrong_count: 2,
      knowledge_ids: ['NODE_1']
    })
  })

  it('writes manual mastery with the cached revision and refreshes the snapshot', async () => {
    await loadLearningState()
    api.updateKnowledgeState.mockResolvedValue({ revision: 4 })
    api.getLearnerState.mockResolvedValue(serverState(4))
    api.getLearnerMistakes.mockResolvedValue(serverMistakes(4))

    await setMastered('NODE_2', '节点二')

    expect(api.updateKnowledgeState).toHaveBeenCalledWith('NODE_2', {
      manual_override: 'mastered',
      node_name: '节点二',
      expected_revision: 3,
      idempotency_key: 'knowledge-mastered:test-key'
    })
    expect(getLearningState().revision).toBe(4)
  })

  it('persists target-scoped plan progress through the learner API', async () => {
    await loadLearningState()
    api.updatePlanStep.mockResolvedValue({ revision: 4 })
    api.getLearnerState.mockResolvedValue({
      ...serverState(4),
      plan_progress: [
        ...serverState(4).plan_progress,
        { target_id: 'TARGET', node_id: 'NODE_3', status: 'completed', completed_at: 12 }
      ]
    })
    api.getLearnerMistakes.mockResolvedValue(serverMistakes(4))

    const done = await togglePlanStep('TARGET', 'NODE_3')

    expect(api.updatePlanStep).toHaveBeenCalledWith('TARGET', 'NODE_3', {
      status: 'completed',
      expected_revision: 3,
      idempotency_key: 'plan-step:test-key'
    })
    expect(done).toEqual(['NODE_2', 'NODE_3'])
  })

  it('does not accept client knowledge IDs when recording an attempt', async () => {
    await loadLearningState()
    api.recordLearnerAttempt.mockResolvedValue({ revision: 4, mistake: null })
    api.getLearnerState.mockResolvedValue(serverState(4))
    api.getLearnerMistakes.mockResolvedValue(serverMistakes(4))

    await recordQuestionAttempt('Q2', {
      correct: false,
      targetId: 'TARGET',
      pathNodeId: 'NODE_2',
      knowledgeIds: ['FORGED']
    })

    expect(api.recordLearnerAttempt).toHaveBeenCalledWith({
      question_id: 'Q2',
      target_id: 'TARGET',
      path_node_id: 'NODE_2',
      correct: false,
      source_page: 'graph',
      expected_revision: 3,
      idempotency_key: 'attempt:test-key'
    })
  })

  it('exports a read-only local-v1 backup and imports it through the API', async () => {
    await loadLearningState()
    api.importLocalV1.mockResolvedValue({ revision: 4, imported: { mastered: 1 } })
    api.getLearnerState.mockResolvedValue(serverState(4))
    api.getLearnerMistakes.mockResolvedValue(serverMistakes(4))
    const exported = exportLearningState()

    const report = await importLearningState(exported)

    expect(JSON.parse(exported).version).toBe(1)
    expect(report.imported.mastered).toBe(1)
    expect(api.importLocalV1).toHaveBeenCalledWith(
      expect.objectContaining({ version: 1 }),
      { expectedRevision: 3, preview: false }
    )
  })

  it('reads legacy state only for a confirmed, idempotent migration', async () => {
    localStorage.setItem('kg_learning_state_v1', JSON.stringify({
      version: 1,
      mastered: { NODE_OLD: {} },
      progress: {},
      mistakes: {},
      plan_done: {}
    }))
    await loadLearningState()
    api.importLocalV1.mockResolvedValue({
      revision: 4,
      content_hash: 'hash-1',
      imported: { mastered: 1 }
    })
    api.getLearnerState.mockResolvedValue(serverState(4))
    api.getLearnerMistakes.mockResolvedValue(serverMistakes(4))

    expect(legacyMigrationPending()).toBe(true)
    await migrateLegacyLearningState()

    expect(api.importLocalV1).toHaveBeenCalledWith(
      expect.objectContaining({ mastered: { NODE_OLD: {} } }),
      { expectedRevision: 3, preview: false }
    )
    expect(localStorage.getItem('kg_learning_state_v1')).not.toBeNull()
    expect(legacyMigrationPending()).toBe(false)
  })
})
