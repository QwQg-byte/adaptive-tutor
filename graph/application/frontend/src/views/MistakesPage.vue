<template>
  <div class="mistakes-page">
    <header class="page-header">
      <div>
        <h2>错题本</h2>
        <p>{{ pendingCount }} 道待复习，累计记录 {{ totalCount }} 道错题</p>
      </div>
      <div class="data-actions">
        <el-tag size="small" effect="plain">状态 v{{ stateRevision }}</el-tag>
        <el-button @click="downloadLearningData">
          <el-icon><Download /></el-icon>
          导出学习数据
        </el-button>
        <el-button type="primary" plain @click="selectImportFile">
          <el-icon><Upload /></el-icon>
          导入学习数据
        </el-button>
        <input
          ref="fileInputRef"
          class="file-input"
          type="file"
          accept="application/json,.json"
          @change="handleImportFile"
        >
      </div>
    </header>

    <section v-if="weakSpots.length" class="weak-spots" aria-label="薄弱知识点">
      <span class="weak-spots-label">薄弱知识点</span>
      <button
        v-for="spot in weakSpots"
        :key="spot.id"
        type="button"
        class="weak-spot-item"
        :class="{ active: knowledgeFilter === spot.id }"
        @click="toggleWeakSpotFilter(spot)"
      >
        <span class="weak-spot-name">{{ spot.name }}</span>
        <span class="weak-spot-count">{{ spot.count }}</span>
      </button>
    </section>

    <section class="filter-bar" aria-label="错题筛选">
      <el-radio-group v-model="statusFilter" size="small">
        <el-radio-button label="unresolved">待复习</el-radio-button>
        <el-radio-button label="resolved">已复习</el-radio-button>
        <el-radio-button label="all">全部</el-radio-button>
      </el-radio-group>
      <el-select v-model="difficultyFilter" clearable placeholder="全部难度" size="small">
        <el-option
          v-for="difficulty in difficulties"
          :key="difficulty"
          :label="difficulty"
          :value="difficulty"
        />
      </el-select>
      <el-select v-model="chapterFilter" clearable placeholder="全部章节" size="small" filterable>
        <el-option-group
          v-for="group in groupedChapters"
          :key="group.id"
          :label="group.name"
        >
          <el-option
            v-for="chapter in group.chapters"
            :key="chapter.id"
            :label="chapter.name"
            :value="String(chapter.id)"
          />
        </el-option-group>
      </el-select>
      <el-tag v-if="knowledgeFilter" closable type="primary" @close="clearKnowledgeFilter">
        知识点：{{ knowledgeFilterLabel }}
      </el-tag>
      <span class="filter-result">{{ filteredItems.length }} 道</span>
      <el-tooltip content="刷新错题详情" placement="top">
        <el-button circle :loading="loading" aria-label="刷新错题详情" @click="loadMistakes">
          <el-icon><Refresh /></el-icon>
        </el-button>
      </el-tooltip>
    </section>

    <el-table
      v-loading="loading"
      :data="filteredItems"
      row-key="question_id"
      class="mistakes-table"
      height="calc(100vh - 310px)"
      :expand-row-keys="expandedRows"
      @expand-change="handleExpandChange"
    >
      <el-table-column type="expand">
        <template #default="{ row }">
          <div v-if="row.dependencies_loading" class="dependencies-loading">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>分析前置依赖中...</span>
          </div>
          <div v-else-if="row.dependencies_error" class="dependencies-error">
            <el-icon><Warning /></el-icon>
            <span>{{ row.dependencies_error }}</span>
          </div>
          <div v-else-if="row.weak_prerequisites" class="dependencies-result">
            <div class="dep-section">
              <h4>📥 前置依赖检查</h4>
              <div v-if="row.weak_prerequisites.length === 0" class="dep-all-ok">
                <el-icon color="#67c23a"><CircleCheck /></el-icon>
                <span>前置知识点均已掌握</span>
              </div>
              <div v-else class="dep-weak-list">
                <div class="dep-weak-header">
                  <el-icon color="#e6a23c"><Warning /></el-icon>
                  <span>尚未掌握 {{ row.weak_prerequisites.length }} 个前置知识点：</span>
                </div>
                <div class="dep-weak-items">
                  <el-tag
                    v-for="dep in row.weak_prerequisites"
                    :key="dep.id"
                    :type="dep.status === 'not_started' ? 'danger' : 'warning'"
                    effect="plain"
                    class="dep-tag"
                    @click="openKnowledge(dep)"
                  >
                    {{ dep.name }}
                    <span class="dep-status">{{ dep.status === 'not_started' ? '未开始' : '学习中' }}</span>
                  </el-tag>
                </div>
                <div class="dep-suggestion">
                  💡 建议先学习这些前置知识点，再复习本题
                </div>
              </div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="题目" min-width="230">
        <template #default="{ row }">
          <button type="button" class="question-link" @click="openQuestion(row.question_id)">
            <span>{{ row.question.name || row.question_id }}</span>
            <small>{{ row.question_id }}</small>
          </button>
        </template>
      </el-table-column>
      <el-table-column label="难度" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.question.difficulty" size="small" effect="plain">
            {{ row.question.difficulty }}
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="关联知识点" min-width="280">
        <template #default="{ row }">
          <div v-if="row.knowledge_points.length" class="knowledge-links">
            <el-button
              v-for="kp in row.knowledge_points"
              :key="kp.node_id || kp.id"
              link
              type="primary"
              size="small"
              @click="openKnowledge(kp)"
            >
              {{ kp.name }}
            </el-button>
          </div>
          <span v-else class="muted-text">暂无关联</span>
        </template>
      </el-table-column>
      <el-table-column label="记录" width="100">
        <template #default="{ row }">
          <span class="attempt-count">错 {{ row.wrong_count }} / 做 {{ row.attempts }}</span>
        </template>
      </el-table-column>
      <el-table-column label="最近作答" width="150">
        <template #default="{ row }">{{ formatDate(row.last_attempt_at) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.unresolved ? 'danger' : 'success'" size="small">
            {{ row.unresolved ? '待复习' : '已复习' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="学习路径" width="130">
        <template #default="{ row }">
          <el-button v-if="row.target_id" link type="primary" @click="openPath(row)">
            {{ row.path_node_id || row.target_id }}
          </el-button>
          <span v-else class="muted-text">全局练习</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="190" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openQuestion(row.question_id)">
            <el-icon><View /></el-icon>
            查看题目
          </el-button>
          <el-button v-if="row.unresolved" link type="success" @click="markReviewed(row)">
            <el-icon><CircleCheck /></el-icon>
            标记已复习
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty :description="emptyDescription" />
      </template>
    </el-table>

    <!-- 二次验证对话框 -->
    <el-dialog
      v-model="verifyDialogVisible"
      title="验证复习效果"
      width="600px"
      :close-on-click-modal="false"
    >
      <div v-if="verifyLoading" class="verify-loading">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <p>正在获取验证题目...</p>
      </div>
      <div v-else-if="verifyQuestion" class="verify-content">
        <div class="verify-header">
          <el-icon color="#409eff" :size="20"><QuestionFilled /></el-icon>
          <span class="verify-title">请完成以下题目来验证复习效果</span>
        </div>
        <div class="verify-question">
          <div class="verify-question-name">
            {{ verifyQuestion.name || verifyQuestion.id }}
          </div>
          <div class="verify-question-meta">
            <el-tag v-if="verifyQuestion.difficulty" size="small" effect="plain">
              {{ verifyQuestion.difficulty }}
            </el-tag>
            <el-button
              link
              type="primary"
              size="small"
              @click="() => window.open(`/questions?id=${verifyQuestion.id}`, '_blank')"
            >
              查看完整题目 →
            </el-button>
          </div>
        </div>
        <div class="verify-hint">
          💡 请打开题目链接作答，然后在下方选择你的作答结果
        </div>
      </div>
      <template #footer>
        <div v-if="!verifyLoading && verifyQuestion" class="verify-actions">
          <el-button @click="skipVerification">跳过验证</el-button>
          <el-button type="danger" plain @click="handleVerifyResult(false)">
            <el-icon><Close /></el-icon>
            做错了
          </el-button>
          <el-button type="success" @click="handleVerifyResult(true)">
            <el-icon><Check /></el-icon>
            做对了
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheck, Download, Refresh, Upload, View, Loading, Warning, QuestionFilled, Check, Close } from '@element-plus/icons-vue'
import { getKnowledgePoints, getQuestionCategories, getQuestionDetail, getQuestionsByKnowledge } from '@/api/graph'
import { getDependencies } from '@/api/path'
import {
  exportLearningState,
  getMistakes,
  getNodeProgress,
  getRevision,
  importLearningState,
  loadLearningState,
  recordQuestionAttempt,
  resolveMistake
} from '@/stores/progress'
import { learnerErrorMessage } from '@/api/learner'

const route = useRoute()
const router = useRouter()

const items = ref([])
const chapters = ref([])
const difficulties = ref([])
const loading = ref(false)
const stateRevision = ref(0)
const statusFilter = ref('unresolved')
const difficultyFilter = ref('')
const chapterFilter = ref('')
const knowledgeFilter = ref('')
const fileInputRef = ref(null)
const expandedRows = ref([])
const verifyDialogVisible = ref(false)
const verifyingMistake = ref(null)
const verifyQuestion = ref(null)
const verifyLoading = ref(false)
let loadRequestId = 0

const totalCount = computed(() => items.value.length)
const pendingCount = computed(() => items.value.filter(item => item.unresolved).length)

const groupedChapters = computed(() => {
  const groups = new Map()
  chapters.value.forEach(chapter => {
    const id = chapter.course_id
    if (!groups.has(id)) groups.set(id, { id, name: chapter.course_name, chapters: [] })
    groups.get(id).chapters.push(chapter)
  })
  return [...groups.values()]
})

const filteredItems = computed(() => items.value.filter(item => {
  if (statusFilter.value === 'unresolved' && !item.unresolved) return false
  if (statusFilter.value === 'resolved' && item.unresolved) return false
  if (difficultyFilter.value && item.question.difficulty !== difficultyFilter.value) return false
  if (chapterFilter.value && !item.knowledge_points.some(kp => String(kp.chapter_id) === chapterFilter.value)) {
    return false
  }
  if (knowledgeFilter.value) {
    const ids = item.knowledge_points.flatMap(kp => [kp.node_id, kp.id]).filter(Boolean).map(String)
    if (!ids.includes(knowledgeFilter.value)) return false
  }
  return true
}))

const weakSpots = computed(() => {
  const counts = new Map()
  items.value
    .filter(item => item.unresolved)
    .forEach(item => {
      item.knowledge_points.forEach(kp => {
        const id = String(kp.node_id || kp.id || '')
        if (!id) return
        const current = counts.get(id) || { id, name: kp.name || id, count: 0 }
        current.count += 1
        counts.set(id, current)
      })
    })
  return [...counts.values()]
    .sort((a, b) => b.count - a.count)
    .slice(0, 5)
})

function toggleWeakSpotFilter(spot) {
  const query = { ...route.query }
  if (knowledgeFilter.value === spot.id) {
    delete query.knowledge_id
  } else {
    query.knowledge_id = spot.id
  }
  router.replace({ path: route.path, query })
}

const knowledgeFilterLabel = computed(() => {
  for (const item of items.value) {
    const match = item.knowledge_points.find(kp => (
      String(kp.node_id || '') === knowledgeFilter.value || String(kp.id || '') === knowledgeFilter.value
    ))
    if (match?.name) return match.name
  }
  return knowledgeFilter.value
})

const emptyDescription = computed(() => (
  totalCount.value === 0 ? '还没有错题记录' : '当前筛选条件下没有错题'
))

async function loadReferenceData() {
  const [chapterResult, categoryResult] = await Promise.allSettled([
    getKnowledgePoints(100, 'Chapter'),
    getQuestionCategories()
  ])

  const chapterResponse = chapterResult.status === 'fulfilled' ? chapterResult.value : null
  if (chapterResponse?.success && Array.isArray(chapterResponse.data)) {
    chapters.value = chapterResponse.data
      .filter(chapter => chapter.order != null)
      .sort((a, b) => a.order - b.order)
      .map(chapter => ({
        id: chapter.order,
        name: chapter.title || chapter.name,
        course_id: chapter.order <= 12 ? 'data-structures' : 'algorithms',
        course_name: chapter.order <= 12 ? '数据结构' : '算法设计'
      }))
  }

  const categoryResponse = categoryResult.status === 'fulfilled' ? categoryResult.value : null
  if (categoryResponse?.success) {
    difficulties.value = (categoryResponse.data?.difficulties || [])
      .map(item => item.difficulty)
      .filter(Boolean)
  }
}

async function fetchMistakeDetail(record) {
  try {
    const response = await getQuestionDetail(record.question_id)
    if (response?.success && response.data) {
      return {
        ...record,
        question: response.data.question || { id: record.question_id },
        knowledge_points: response.data.knowledge_points || []
      }
    }
  } catch (error) {
    console.error(`加载错题 ${record.question_id} 失败:`, error)
  }
  return {
    ...record,
    question: { id: record.question_id, name: record.question_id },
    knowledge_points: [],
    load_failed: true
  }
}

async function loadMistakes() {
  const requestId = ++loadRequestId
  loading.value = true
  try {
    await loadLearningState({ force: true })
    stateRevision.value = getRevision()
    const records = getMistakes({ includeResolved: true })
      .filter(record => record.wrong_count > 0)
      .sort((a, b) => String(b.last_attempt_at).localeCompare(String(a.last_attempt_at)))
    const detailed = []
    for (let index = 0; index < records.length; index += 8) {
      const batch = await Promise.all(records.slice(index, index + 8).map(fetchMistakeDetail))
      if (requestId !== loadRequestId) return
      detailed.push(...batch)
    }
    items.value = detailed
  } catch (error) {
    console.error('加载错题失败:', error)
    ElMessage.error(learnerErrorMessage(error, '加载错题失败'))
  } finally {
    if (requestId === loadRequestId) loading.value = false
  }
}

function markReviewed(row) {
  startVerification(row)
}

async function startVerification(row) {
  if (!row.knowledge_points || row.knowledge_points.length === 0) {
    await confirmDirectResolve(row, '该题目没有关联知识点，无法进行验证')
    return
  }

  verifyingMistake.value = row
  verifyLoading.value = true
  verifyDialogVisible.value = true
  verifyQuestion.value = null

  try {
    const knowledgePoint = row.knowledge_points[0]
    const response = await getQuestionsByKnowledge(knowledgePoint.node_id || knowledgePoint.id, 10)

    if (!response.success || !response.data || response.data.length === 0) {
      await confirmDirectResolve(row, '该知识点暂无其他题目可用于验证')
      return
    }

    const candidates = response.data.filter(q => q.id !== row.question_id)
    if (candidates.length === 0) {
      await confirmDirectResolve(row, '该知识点暂无其他题目可用于验证')
      return
    }

    const randomIndex = Math.floor(Math.random() * candidates.length)
    verifyQuestion.value = candidates[randomIndex]
  } catch (error) {
    console.error('获取验证题目失败:', error)
    await confirmDirectResolve(row, '获取验证题目失败')
  } finally {
    verifyLoading.value = false
  }
}

async function confirmDirectResolve(row, reason) {
  verifyDialogVisible.value = false
  try {
    await ElMessageBox.confirm(
      `${reason}，是否直接标记为已复习？`,
      '无法验证',
      {
        type: 'warning',
        confirmButtonText: '直接标记',
        cancelButtonText: '取消'
      }
    )
    await resolveMistake(row.question_id)
    row.unresolved = false
    row.resolved_at = new Date().toISOString()
    ElMessage.success('已标记为复习完成')
  } catch {
    // 用户取消
  }
}

async function handleVerifyResult(correct) {
  if (!verifyingMistake.value || !verifyQuestion.value) return

  const row = verifyingMistake.value
  const verifyQuestionId = verifyQuestion.value.id

  if (correct) {
    await resolveMistake(row.question_id)
    row.unresolved = false
    row.resolved_at = new Date().toISOString()
    ElMessage.success('验证通过，已标记为复习完成')
  } else {
    await recordQuestionAttempt(verifyQuestionId, { correct: false })
    ElMessage.warning('验证失败，建议继续复习该知识点。验证题已加入错题本')
  }

  verifyDialogVisible.value = false
  verifyingMistake.value = null
  verifyQuestion.value = null
}

async function skipVerification() {
  if (!verifyingMistake.value) return

  const row = verifyingMistake.value
  await resolveMistake(row.question_id)
  row.unresolved = false
  row.resolved_at = new Date().toISOString()
  ElMessage.success('已跳过验证，标记为复习完成')

  verifyDialogVisible.value = false
  verifyingMistake.value = null
  verifyQuestion.value = null
}

function openQuestion(questionId) {
  router.push({ path: '/questions', query: { id: questionId } })
}

function openKnowledge(knowledgePoint) {
  router.push({
    path: '/knowledge',
    query: { focus: knowledgePoint.node_id || knowledgePoint.id || knowledgePoint.name }
  })
}

function openPath(row) {
  router.push({ path: '/path', query: { target: row.target_id, auto: '1' } })
}

function formatDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).format(date)
}

function downloadLearningData() {
  const blob = new Blob([exportLearningState()], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `knowledge-learning-data-${new Date().toISOString().slice(0, 10)}.json`
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success('学习数据已导出')
}

function selectImportFile() {
  fileInputRef.value?.click()
}

async function handleImportFile(event) {
  const input = event.target
  const file = input.files?.[0]
  if (!file) return

  try {
    if (file.size > 2 * 1024 * 1024) throw new Error('学习数据文件不能超过 2MB')
    const content = await file.text()
    await ElMessageBox.confirm(
      '导入记录将按证据优先级合并到当前学习档案。',
      '确认导入学习数据',
      { type: 'info', confirmButtonText: '导入', cancelButtonText: '取消' }
    )
    const report = await importLearningState(content)
    await loadMistakes()
    const count = Object.values(report.imported || {}).reduce((sum, value) => sum + value, 0)
    ElMessage.success(`已导入 ${count} 项学习记录`)
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(learnerErrorMessage(error, error?.message || '学习数据导入失败'))
    }
  } finally {
    input.value = ''
  }
}

function syncKnowledgeFilter() {
  const value = route.query.knowledge_id
  knowledgeFilter.value = String(Array.isArray(value) ? value[0] || '' : value || '')
}

function clearKnowledgeFilter() {
  const query = { ...route.query }
  delete query.knowledge_id
  router.replace({ path: route.path, query })
}

async function handleExpandChange(row, expandedRowsData) {
  const isExpanding = expandedRowsData.some(r => r.question_id === row.question_id)

  if (isExpanding && !row.dependencies_loaded && !row.dependencies_loading) {
    await loadDependencies(row)
  }
}

async function loadDependencies(row) {
  if (!row.knowledge_points || row.knowledge_points.length === 0) {
    row.weak_prerequisites = []
    row.dependencies_loaded = true
    return
  }

  row.dependencies_loading = true
  row.dependencies_error = null

  try {
    const allPrerequisites = new Map()

    for (const kp of row.knowledge_points) {
      try {
        const response = await getDependencies(kp.name, 2)
        if (response.success && response.data && response.data.prerequisites) {
          response.data.prerequisites.forEach(dep => {
            const id = dep.id || dep.node_id || dep.name
            if (id && !allPrerequisites.has(id)) {
              allPrerequisites.set(id, dep)
            }
          })
        }
      } catch (error) {
        console.warn(`获取 ${kp.name} 的依赖失败:`, error)
      }
    }

    const weakPrerequisites = []
    for (const dep of allPrerequisites.values()) {
      const id = dep.id || dep.node_id
      if (!id) continue

      const progress = getNodeProgress(id)
      if (progress && progress.status !== 'mastered') {
        weakPrerequisites.push({
          id,
          name: dep.name,
          node_id: id,
          status: progress.status
        })
      }
    }

    row.weak_prerequisites = weakPrerequisites
    row.dependencies_loaded = true
  } catch (error) {
    console.error('加载依赖分析失败:', error)
    row.dependencies_error = '加载依赖分析失败，请稍后重试'
  } finally {
    row.dependencies_loading = false
  }
}

watch(() => route.query.knowledge_id, syncKnowledgeFilter)

onMounted(async () => {
  syncKnowledgeFilter()
  await Promise.all([loadReferenceData(), loadMistakes()])
})
</script>

<style scoped>
.mistakes-page {
  max-width: 1440px;
  margin: 0 auto;
  min-height: calc(100vh - 160px);
}

.page-header,
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-header {
  justify-content: space-between;
  margin-bottom: 14px;
}

.page-header h2 {
  margin: 0 0 4px;
  color: #303133;
  font-size: 22px;
}

.page-header p {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.data-actions {
  display: flex;
  gap: 8px;
}

.data-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.file-input {
  display: none;
}

.local-data-alert {
  margin-bottom: 14px;
}

.weak-spots {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 0;
}

.weak-spots-label {
  color: #909399;
  font-size: 13px;
  margin-right: 4px;
}

.weak-spot-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid #f56c6c;
  border-radius: 14px;
  background: #fef0f0;
  color: #f56c6c;
  font-size: 13px;
  cursor: pointer;
}

.weak-spot-item.active {
  background: #f56c6c;
  color: #fff;
}

.weak-spot-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  border-radius: 9px;
  background: rgba(0, 0, 0, 0.08);
  font-size: 12px;
}

.filter-bar {
  padding: 12px 0;
  border-top: 1px solid #e4e7ed;
}

.filter-bar :deep(.el-select) {
  width: 180px;
}

.filter-result {
  margin-left: auto;
  color: #909399;
  font-size: 13px;
}

.mistakes-table {
  width: 100%;
  border-top: 1px solid #ebeef5;
}

.question-link {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
  max-width: 100%;
  padding: 0;
  color: #303133;
  background: transparent;
  border: 0;
  cursor: pointer;
  text-align: left;
}

.question-link:hover span {
  color: #409eff;
}

.question-link small,
.muted-text {
  color: #909399;
}

.knowledge-links {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 8px;
}

.knowledge-links :deep(.el-button + .el-button) {
  margin-left: 0;
}

.attempt-count {
  color: #606266;
  font-size: 13px;
}

.dependencies-loading,
.dependencies-error,
.dependencies-result {
  padding: 16px 20px;
  background: #f5f7fa;
  border-radius: 4px;
  margin: 8px 48px;
}

.dependencies-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #909399;
  font-size: 13px;
}

.dependencies-error {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #f56c6c;
  font-size: 13px;
}

.dependencies-result {
  background: white;
  border: 1px solid #e4e7ed;
}

.dep-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
}

.dep-all-ok {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f0f9eb;
  border-radius: 4px;
  color: #67c23a;
  font-size: 13px;
}

.dep-weak-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dep-weak-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #e6a23c;
  font-weight: 500;
}

.dep-weak-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-left: 24px;
}

.dep-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.dep-tag:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.dep-status {
  margin-left: 4px;
  opacity: 0.8;
  font-size: 11px;
}

.dep-suggestion {
  padding: 8px 12px;
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}

.verify-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  gap: 12px;
}

.verify-loading p {
  margin: 0;
  color: #909399;
  font-size: 14px;
}

.verify-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.verify-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e4e7ed;
}

.verify-title {
  font-size: 15px;
  font-weight: 500;
  color: #303133;
}

.verify-question {
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}

.verify-question-name {
  font-size: 14px;
  color: #303133;
  line-height: 1.6;
  margin-bottom: 12px;
}

.verify-question-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.verify-hint {
  padding: 12px;
  background: #ecf5ff;
  border-left: 3px solid #409eff;
  border-radius: 4px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}

.verify-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
</style>
