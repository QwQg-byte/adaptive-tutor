export const LEARNING_STATUS_META = Object.freeze({
  mastered: Object.freeze({ label: '已掌握', color: '#67c23a' }),
  in_progress: Object.freeze({ label: '学习中', color: '#e6a23c' }),
  not_started: Object.freeze({ label: '未开始', color: '#c0c4cc' })
})

export const MASTERY_STATE_META = Object.freeze({
  assessed_mastery: Object.freeze({ label: '测评已掌握', color: '#4f9d69', border: '#2f6f46' }),
  self_reported_mastery: Object.freeze({ label: '自报已掌握', color: '#3a9d9a', border: '#236b69' }),
  soft_confidence: Object.freeze({ label: '较可能掌握', color: '#5b8def', border: '#365fa8' }),
  weak: Object.freeze({ label: '薄弱', color: '#e6a23c', border: '#9a651c' }),
  untested: Object.freeze({ label: '未测试', color: '#c0c4cc', border: '#7d838a' })
})

export function getMasteryState(progress, masteredRecord = null) {
  if (MASTERY_STATE_META[progress?.mastery_state]) return progress.mastery_state
  if (masteredRecord || progress?.status === 'mastered') return 'assessed_mastery'
  if (progress && (progress.status !== 'not_started' || Number(progress.mastery) > 0)) return 'weak'
  return 'untested'
}

export function getLearningStatus(progress, masteredRecord = null) {
  const mastery = Number(progress?.mastery) || 0
  if (masteredRecord || progress?.status === 'mastered' || mastery >= 100) {
    return 'mastered'
  }
  if (progress && (progress.status !== 'not_started' || mastery > 0)) {
    return 'in_progress'
  }
  return 'not_started'
}

export function getKnowledgeNodeId(node) {
  return String(node?.id || node?.node_id || '').trim()
}

function timestampValue(record) {
  const value = record?.last_seen_at || record?.updated_at || record?.completed_at
  const timestamp = Date.parse(value || '')
  return Number.isFinite(timestamp) ? timestamp : 0
}

function chapterIdentity(chapter) {
  const explicitOrder = chapter?.order ?? chapter?.chapter_id
  const idMatch = String(chapter?.id || chapter?.node_id || '').match(/(\d+)$/)
  const order = Number(explicitOrder ?? idMatch?.[1])
  return {
    key: Number.isFinite(order) ? String(order) : String(chapter?.id || chapter?.node_id || ''),
    order: Number.isFinite(order) ? order : Number.MAX_SAFE_INTEGER,
    id: String(chapter?.id || chapter?.node_id || explicitOrder || ''),
    name: chapter?.title || chapter?.name || (Number.isFinite(order) ? `第 ${order} 章` : '未分章')
  }
}

function emptyStatusCounts() {
  return { mastered: 0, in_progress: 0, not_started: 0 }
}

export function buildLearningDashboard(knowledgePoints = [], chapters = [], state = {}) {
  const progress = state.progress || {}
  const mastered = state.mastered || {}
  const mistakes = state.mistakes || {}
  const chapterLookup = new Map()

  chapters.forEach(chapter => {
    const identity = chapterIdentity(chapter)
    if (identity.key) chapterLookup.set(identity.key, identity)
    if (identity.id) chapterLookup.set(identity.id, identity)
  })

  const summary = { total: 0, ...emptyStatusCounts(), mastery_percent: 0 }
  const chapterGroups = new Map()
  const nodeRows = []
  let masteryTotal = 0

  knowledgePoints.forEach((node, index) => {
    const id = getKnowledgeNodeId(node)
    if (!id) return
    const nodeProgress = progress[id] || null
    const status = getLearningStatus(nodeProgress, mastered[id])
    const mastery = status === 'mastered'
      ? 100
      : Math.min(99, Math.max(0, Number(nodeProgress?.mastery) || 0))
    const rawChapterKey = node.chapter_id ?? 'unassigned'
    const chapterKey = String(rawChapterKey)
    const chapter = chapterLookup.get(chapterKey) || {
      key: chapterKey,
      order: Number.isFinite(Number(rawChapterKey)) ? Number(rawChapterKey) : Number.MAX_SAFE_INTEGER,
      id: chapterKey,
      name: rawChapterKey === 'unassigned' ? '未分章' : `第 ${rawChapterKey} 章`
    }

    if (!chapterGroups.has(chapterKey)) {
      chapterGroups.set(chapterKey, {
        ...chapter,
        total: 0,
        ...emptyStatusCounts(),
        mastery_total: 0
      })
    }
    const group = chapterGroups.get(chapterKey)
    group.total += 1
    group[status] += 1
    group.mastery_total += mastery

    summary.total += 1
    summary[status] += 1
    masteryTotal += mastery
    nodeRows.push({ ...node, id, status, mastery, progress: nodeProgress, source_index: index })
  })

  summary.mastery_percent = summary.total ? Math.round(masteryTotal / summary.total) : 0

  const chapter_progress = [...chapterGroups.values()]
    .map(group => ({
      id: group.id,
      name: group.name,
      order: group.order,
      total: group.total,
      mastered: group.mastered,
      in_progress: group.in_progress,
      not_started: group.not_started,
      mastery_percent: group.total ? Math.round(group.mastery_total / group.total) : 0
    }))
    .sort((a, b) => a.order - b.order || a.name.localeCompare(b.name, 'zh-CN'))

  const recent = nodeRows
    .filter(row => row.status !== 'not_started' && timestampValue(row.progress) > 0)
    .sort((a, b) => timestampValue(b.progress) - timestampValue(a.progress) || a.source_index - b.source_index)
    .slice(0, 6)
    .map(row => {
      const result = {
        ...row,
        last_activity_at: row.progress?.last_seen_at || row.progress?.updated_at || row.progress?.completed_at
      }
      delete result.source_index
      return result
    })

  const recommendationRow = recent.find(row => row.status === 'in_progress')
    || nodeRows.find(row => row.status === 'in_progress')
    || nodeRows.find(row => row.status === 'not_started')
    || null
  const recommendation = recommendationRow
    ? {
        id: recommendationRow.id,
        name: recommendationRow.name || recommendationRow.id,
        status: recommendationRow.status,
        chapter_id: recommendationRow.chapter_id ?? null,
        reason: recommendationRow.status === 'in_progress' ? '继续最近的学习内容' : '从尚未学习的知识点开始'
      }
    : null

  const mistakeRows = Object.values(mistakes).filter(value => value && typeof value === 'object')
  const mistake_summary = {
    total: mistakeRows.length,
    unresolved: mistakeRows.filter(record => record.unresolved !== false).length,
    resolved: mistakeRows.filter(record => record.unresolved === false).length,
    wrong_attempts: mistakeRows.reduce((sum, record) => sum + Math.max(0, Number(record.wrong_count) || 0), 0)
  }

  return { summary, chapter_progress, mistake_summary, recent, recommendation }
}
