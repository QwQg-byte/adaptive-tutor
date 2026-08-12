/**
 * Learner-state cache.
 *
 * SQLite behind the Tutor API is the only fact source. The legacy localStorage
 * document is read only for one-time migration and never receives new writes.
 */

import {
  createIdempotencyKey,
  getLearnerMistakes,
  getLearnerState,
  getStudentId,
  importLocalV1,
  isRevisionConflict,
  recordLearnerAttempt,
  updateKnowledgeState,
  updateMistakeState,
  updatePlanStep
} from '@/api/learner'

const LEGACY_STATE_KEY = 'kg_learning_state_v1'
const LEGACY_MASTERED_KEY = 'kg_mastered_nodes'
const LEGACY_PLAN_DONE_KEY = 'kg_plan_done_steps'
const MIGRATION_MARKER_PREFIX = 'kg_learning_state_v1_migrated:'

let cache = emptyCache()
let loadingPromise = null
const listeners = new Set()

function emptyCache() {
  return {
    student_id: getStudentId(),
    revision: 0,
    loaded: false,
    mastery_nodes: [],
    plan_progress: [],
    mistakes: [],
    recent_events: [],
    mistake_summary: { total: 0, open: 0, resolved: 0, wrong_attempts: 0 }
  }
}

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

function emitChange() {
  const snapshot = getLearningState()
  listeners.forEach(listener => listener(snapshot))
}

function applyResponses(state, mistakeResponse) {
  cache = {
    student_id: state.student_id,
    revision: state.revision,
    loaded: true,
    mastery_nodes: state.mastery_nodes || [],
    plan_progress: state.plan_progress || [],
    mistakes: mistakeResponse?.items || state.open_mistakes || [],
    recent_events: state.recent_events || [],
    mistake_summary: state.mistake_summary || {}
  }
  emitChange()
  return getLearningState()
}

async function fetchSnapshot() {
  const studentId = getStudentId()
  let [state, mistakes] = await Promise.all([
    getLearnerState(studentId),
    getLearnerMistakes({}, studentId)
  ])
  if (state.revision !== mistakes.revision) {
    const refreshed = await Promise.all([
      getLearnerState(studentId),
      getLearnerMistakes({}, studentId)
    ])
    state = refreshed[0]
    mistakes = refreshed[1]
  }
  if (state.revision !== mistakes.revision) {
    throw new Error('学习状态版本持续变化，请稍后重试')
  }
  return applyResponses(state, mistakes)
}

export async function loadLearningState({ force = false } = {}) {
  const studentId = getStudentId()
  if (!force && cache.loaded && cache.student_id === studentId) return getLearningState()
  if (!loadingPromise) {
    loadingPromise = fetchSnapshot().finally(() => {
      loadingPromise = null
    })
  }
  return loadingPromise
}

export function invalidateLearningState() {
  cache.loaded = false
}

export function resetLearningStateCache() {
  cache = emptyCache()
  loadingPromise = null
}

export function subscribeLearningState(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function masteryRecord(node) {
  return {
    status: ['assessed_mastery', 'self_reported_mastery'].includes(node.mastery_state)
      ? 'mastered'
      : 'in_progress',
    mastery: Math.round((Number(node.mastery) || 0) * 100),
    mastery_state: node.mastery_state,
    evidence_source: node.evidence_source,
    manual_override: node.manual_override,
    attempts: node.attempts,
    correct: node.correct,
    updated_at: node.updated_at
  }
}

function mistakeRecord(item) {
  return {
    ...item,
    question_id: item.question_id,
    attempts: Number(item.wrong_count || 0) + Number(item.correct_after_wrong_count || 0),
    unresolved: item.status === 'open',
    knowledge_ids: item.primary_node_id ? [item.primary_node_id] : [],
    last_attempt_at: item.updated_at,
    resolved_at: item.resolved_at
  }
}

export function getLearningState() {
  const mastered = {}
  const progress = {}
  cache.mastery_nodes.forEach(node => {
    progress[node.node_id] = masteryRecord(node)
    if (['assessed_mastery', 'self_reported_mastery'].includes(node.mastery_state)) {
      mastered[node.node_id] = {
        updated_at: node.updated_at,
        source: node.manual_override === 'mastered' ? 'manual' : node.evidence_source
      }
    }
  })
  const planDone = {}
  cache.plan_progress.forEach(item => {
    if (item.status !== 'completed') return
    if (!planDone[item.target_id]) planDone[item.target_id] = {}
    planDone[item.target_id][item.node_id] = item.completed_at || item.updated_at
  })
  const mistakes = {}
  cache.mistakes.forEach(item => {
    mistakes[item.question_id] = mistakeRecord(item)
  })
  return {
    version: 2,
    student_id: cache.student_id,
    revision: cache.revision,
    loaded: cache.loaded,
    mastered,
    progress,
    mistakes,
    plan_done: planDone,
    recent_events: clone(cache.recent_events),
    mistake_summary: clone(cache.mistake_summary)
  }
}

export function getRevision() {
  return cache.revision
}

export function getMastered() {
  return Object.keys(getLearningState().mastered)
}

export function isMastered(nodeId) {
  return getMastered().includes(nodeId)
}

export function getNodeProgress(nodeId) {
  return getLearningState().progress[nodeId] || {
    status: 'not_started',
    mastery: 0,
    mastery_state: 'untested',
    updated_at: null
  }
}

async function withRevisionRefresh(operation) {
  if (!cache.loaded) await loadLearningState()
  try {
    const result = await operation(cache.revision)
    await loadLearningState({ force: true })
    return result
  } catch (error) {
    if (isRevisionConflict(error)) await loadLearningState({ force: true })
    throw error
  }
}

export function setMastered(nodeId, nodeName = '') {
  return withRevisionRefresh(revision => updateKnowledgeState(nodeId, {
    manual_override: 'mastered',
    node_name: nodeName,
    expected_revision: revision,
    idempotency_key: createIdempotencyKey('knowledge-mastered')
  }))
}

export function unsetMastered(nodeId, nodeName = '') {
  return withRevisionRefresh(revision => updateKnowledgeState(nodeId, {
    manual_override: null,
    node_name: nodeName,
    expected_revision: revision,
    idempotency_key: createIdempotencyKey('knowledge-clear')
  }))
}

export async function toggleMastered(nodeId, nodeName = '') {
  return isMastered(nodeId)
    ? unsetMastered(nodeId, nodeName)
    : setMastered(nodeId, nodeName)
}

export function getPlanDone(targetId) {
  return cache.plan_progress
    .filter(item => item.target_id === targetId && item.status === 'completed')
    .map(item => item.node_id)
}

export async function togglePlanStep(targetId, nodeId) {
  const completed = getPlanDone(targetId).includes(nodeId)
  await withRevisionRefresh(revision => updatePlanStep(targetId, nodeId, {
    status: completed ? 'in_progress' : 'completed',
    expected_revision: revision,
    idempotency_key: createIdempotencyKey('plan-step')
  }))
  return getPlanDone(targetId)
}

export async function clearPlanDone(targetId) {
  const completed = [...getPlanDone(targetId)]
  for (const nodeId of completed) {
    await withRevisionRefresh(revision => updatePlanStep(targetId, nodeId, {
      status: 'in_progress',
      expected_revision: revision,
      idempotency_key: createIdempotencyKey('plan-reset')
    }))
  }
  return []
}

export async function recordQuestionAttempt(
  questionId,
  { correct = false, targetId = null, pathNodeId = null } = {}
) {
  const result = await withRevisionRefresh(revision => recordLearnerAttempt({
    question_id: questionId,
    target_id: targetId,
    path_node_id: pathNodeId,
    correct,
    source_page: 'graph',
    expected_revision: revision,
    idempotency_key: createIdempotencyKey('attempt')
  }))
  return result.mistake ? mistakeRecord(result.mistake) : null
}

export function getMistakes({ includeResolved = false } = {}) {
  return cache.mistakes
    .map(mistakeRecord)
    .filter(item => includeResolved || item.unresolved)
}

export function getMistake(questionId) {
  const item = cache.mistakes.find(record => record.question_id === questionId)
  return item ? mistakeRecord(item) : null
}

export async function resolveMistake(questionId) {
  await withRevisionRefresh(revision => updateMistakeState(questionId, {
    status: 'resolved',
    resolution: 'manual_review',
    expected_revision: revision,
    idempotency_key: createIdempotencyKey('mistake-resolve')
  }))
  return getMistake(questionId)
}

export function exportLearningState() {
  const state = getLearningState()
  return JSON.stringify({
    version: 1,
    mastered: state.mastered,
    progress: state.progress,
    mistakes: state.mistakes,
    plan_done: state.plan_done,
    exported_at: new Date().toISOString()
  }, null, 2)
}

function parseLocalV1(input) {
  let value = input
  if (typeof value === 'string') {
    try {
      value = JSON.parse(value)
    } catch {
      throw new Error('导入内容不是有效的 JSON')
    }
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('学习数据必须是对象')
  }
  if (Number(value.version) !== 1) throw new Error('不支持的学习数据版本')
  for (const field of ['mastered', 'progress', 'mistakes', 'plan_done']) {
    if (value[field] != null && (typeof value[field] !== 'object' || Array.isArray(value[field]))) {
      throw new Error(`字段 ${field} 格式无效`)
    }
  }
  return {
    version: 1,
    mastered: value.mastered || {},
    progress: value.progress || {},
    mistakes: value.mistakes || {},
    plan_done: value.plan_done || {}
  }
}

export async function importLearningState(input, { preview = false } = {}) {
  const state = parseLocalV1(input)
  if (!cache.loaded) await loadLearningState()
  const report = await importLocalV1(state, {
    expectedRevision: cache.revision,
    preview
  })
  if (!preview) await loadLearningState({ force: true })
  return report
}

function readJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : fallback
  } catch {
    return fallback
  }
}

export function getLegacyLearningState() {
  const current = readJson(LEGACY_STATE_KEY, null)
  if (current?.version === 1) return parseLocalV1(current)
  const mastered = readJson(LEGACY_MASTERED_KEY, {})
  const planDone = readJson(LEGACY_PLAN_DONE_KEY, {})
  if (!Object.keys(mastered).length && !Object.keys(planDone).length) return null
  const normalizedPlan = {}
  Object.entries(planDone).forEach(([targetId, steps]) => {
    normalizedPlan[targetId] = Array.isArray(steps)
      ? Object.fromEntries(steps.map(nodeId => [nodeId, new Date().toISOString()]))
      : steps
  })
  return { version: 1, mastered, progress: {}, mistakes: {}, plan_done: normalizedPlan }
}

export function legacyMigrationPending() {
  const legacy = getLegacyLearningState()
  if (!legacy) return false
  return !localStorage.getItem(`${MIGRATION_MARKER_PREFIX}${getStudentId()}`)
}

export async function migrateLegacyLearningState({ preview = false } = {}) {
  const legacy = getLegacyLearningState()
  if (!legacy) return null
  if (!cache.loaded) await loadLearningState()
  const report = await importLocalV1(legacy, {
    expectedRevision: cache.revision,
    preview
  })
  if (!preview) {
    localStorage.setItem(
      `${MIGRATION_MARKER_PREFIX}${getStudentId()}`,
      report.content_hash
    )
    await loadLearningState({ force: true })
  }
  return report
}
