import { beforeEach, describe, expect, it, vi } from 'vitest'

const client = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  put: vi.fn(),
  interceptors: { response: { use: vi.fn() } }
}))

vi.mock('axios', () => ({
  default: { create: vi.fn(() => client) }
}))

import {
  generateLearnerPlan,
  getLearnerState,
  getStudentId,
  importLocalV1,
  recordLearnerAttempt,
  updatePlanStep
} from './learner'


describe('learner API request mappings', () => {
  beforeEach(() => {
    localStorage.clear()
    window.history.replaceState({}, '', '/')
    vi.clearAllMocks()
  })

  it('uses URL student identity before the cached value', () => {
    localStorage.setItem('adaptive_tutor_student_id', 'cached')
    window.history.replaceState({}, '', '/?student=url-student')

    expect(getStudentId()).toBe('url-student')
    expect(localStorage.getItem('adaptive_tutor_student_id')).toBe('url-student')
  })

  it('maps learner state and plan calls to Tutor routes', () => {
    getLearnerState('student/one')
    generateLearnerPlan({ target: '动态规划', expected_revision: 4 }, 'student/one')

    expect(client.get).toHaveBeenCalledWith('/learners/student%2Fone/state')
    expect(client.post).toHaveBeenCalledWith('/learners/student%2Fone/plans', {
      target: '动态规划',
      expected_revision: 4
    })
  })

  it('keeps attempt attribution server-side and addresses target-scoped steps', () => {
    recordLearnerAttempt({
      question_id: 'Q1',
      correct: false,
      expected_revision: 2,
      idempotency_key: 'attempt:key'
    }, 's1')
    updatePlanStep('TARGET', 'NODE_1', {
      status: 'completed',
      expected_revision: 2,
      idempotency_key: 'step:key'
    }, 's1')

    expect(client.post).toHaveBeenCalledWith('/learners/s1/attempts', {
      question_id: 'Q1',
      correct: false,
      expected_revision: 2,
      idempotency_key: 'attempt:key'
    })
    expect(client.put).toHaveBeenCalledWith('/learners/s1/plans/TARGET/steps/NODE_1', {
      status: 'completed',
      expected_revision: 2,
      idempotency_key: 'step:key'
    })
  })

  it('submits local-v1 import with preview and expected revision', () => {
    const state = { version: 1, mastered: {}, progress: {}, mistakes: {}, plan_done: {} }
    importLocalV1(state, { expectedRevision: 7, preview: true }, 's1')

    expect(client.post).toHaveBeenCalledWith('/learners/s1/imports/local-v1', {
      state,
      expected_revision: 7,
      preview: true
    })
  })
})
