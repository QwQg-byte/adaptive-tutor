import axios from 'axios'

const STUDENT_KEY = 'adaptive_tutor_student_id'

const learnerRequest = axios.create({
  baseURL: '/tutor-api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

learnerRequest.interceptors.response.use(
  response => response.data,
  error => Promise.reject(error)
)

function learnerPath(studentId, suffix = '') {
  return `/learners/${encodeURIComponent(studentId)}${suffix}`
}

export function getStudentId() {
  const fromUrl = new URLSearchParams(window.location.search).get('student')?.trim()
  const cached = localStorage.getItem(STUDENT_KEY)?.trim()
  const studentId = fromUrl || cached || 'demo_student'
  localStorage.setItem(STUDENT_KEY, studentId)
  return studentId
}

export function setStudentId(studentId) {
  const normalized = String(studentId || '').trim() || 'demo_student'
  localStorage.setItem(STUDENT_KEY, normalized)
  return normalized
}

export function createIdempotencyKey(prefix = 'write') {
  const id = globalThis.crypto?.randomUUID?.()
    || `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}:${id}`
}

export function getLearnerState(studentId = getStudentId()) {
  return learnerRequest.get(learnerPath(studentId, '/state'))
}

export function getLearnerDashboard(studentId = getStudentId()) {
  return learnerRequest.get(learnerPath(studentId, '/dashboard'))
}

export function generateLearnerPlan(data, studentId = getStudentId()) {
  return learnerRequest.post(learnerPath(studentId, '/plans'), data)
}

export function updateKnowledgeState(nodeId, data, studentId = getStudentId()) {
  return learnerRequest.patch(
    learnerPath(studentId, `/knowledge/${encodeURIComponent(nodeId)}`),
    data
  )
}

export function updatePlanStep(targetId, nodeId, data, studentId = getStudentId()) {
  return learnerRequest.put(
    learnerPath(
      studentId,
      `/plans/${encodeURIComponent(targetId)}/steps/${encodeURIComponent(nodeId)}`
    ),
    data
  )
}

export function recordLearnerAttempt(data, studentId = getStudentId()) {
  return learnerRequest.post(learnerPath(studentId, '/attempts'), data)
}

export function getLearnerMistakes(params = {}, studentId = getStudentId()) {
  return learnerRequest.get(learnerPath(studentId, '/mistakes'), { params })
}

export function updateMistakeState(questionId, data, studentId = getStudentId()) {
  return learnerRequest.patch(
    learnerPath(studentId, `/mistakes/${encodeURIComponent(questionId)}`),
    data
  )
}

export function importLocalV1(state, { expectedRevision = null, preview = false } = {}, studentId = getStudentId()) {
  return learnerRequest.post(learnerPath(studentId, '/imports/local-v1'), {
    state,
    expected_revision: expectedRevision,
    preview
  })
}

export function isRevisionConflict(error) {
  return error?.response?.status === 409
    && error?.response?.data?.error?.code === 'revision_conflict'
}

export function learnerErrorMessage(error, fallback = '学习状态操作失败') {
  return error?.response?.data?.error?.message || fallback
}
