<template>
  <div class="dashboard-page" v-loading="loading">
    <div class="dashboard-header">
      <div>
        <h1>学习总览</h1>
        <p>掌握进度、错题和最近学习</p>
      </div>
      <div class="header-actions">
        <el-tag v-if="dashboard.revision != null" size="small" effect="plain">
          状态 v{{ dashboard.revision }}
        </el-tag>
        <el-button @click="router.push({ path: '/graph', query: { mastery: '1' } })">
          <el-icon><Share /></el-icon>
          掌握度图谱
        </el-button>
        <el-button type="primary" @click="goToPlan(dashboard.recommendation)">
          <el-icon><Guide /></el-icon>
          学习计划
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="load-alert"
    >
      <el-button size="small" @click="loadDashboard">重新加载</el-button>
    </el-alert>

    <template v-else>
      <section class="overview-grid">
        <el-card class="mastery-card" shadow="hover">
          <div class="mastery-content">
            <el-progress
              type="dashboard"
              :percentage="dashboard.summary.mastery_percent"
              :width="150"
              :stroke-width="12"
              color="#409eff"
            >
              <template #default="{ percentage }">
                <strong>{{ percentage }}%</strong>
                <span>综合掌握度</span>
              </template>
            </el-progress>
            <div class="mastery-copy">
              <span class="eyebrow">知识点学习进度</span>
              <strong>{{ dashboard.summary.total }} 个知识点</strong>
              <p>综合掌握度按诊断与练习证据计算。</p>
            </div>
          </div>
        </el-card>

        <el-card
          v-for="item in statusCards"
          :key="item.key"
          class="status-card"
          shadow="hover"
          :style="{ '--status-color': item.color }"
        >
          <span class="status-dot"></span>
          <div class="status-value">{{ item.value }}</div>
          <div class="status-label">{{ item.label }}</div>
          <div class="status-percent">{{ statusPercent(item.value) }}%</div>
        </el-card>
      </section>

      <section class="dashboard-grid">
        <el-card class="chapter-card" shadow="never">
          <template #header>
            <div class="card-title">
              <span><el-icon><Histogram /></el-icon> 分章节掌握度</span>
              <small>{{ dashboard.chapter_progress.length }} 个章节</small>
            </div>
          </template>
          <div v-if="dashboard.chapter_progress.length" class="chapter-list">
            <div v-for="chapter in dashboard.chapter_progress" :key="chapter.id" class="chapter-row">
              <div class="chapter-heading">
                <div>
                  <strong>{{ chapter.name }}</strong>
                  <span>{{ chapter.total }} 个知识点</span>
                </div>
                <b>{{ chapter.mastery_percent }}%</b>
              </div>
              <div class="status-bar" :title="chapterBarTitle(chapter)">
                <span
                  class="mastered"
                  :style="{ width: segmentWidth(chapter.mastered, chapter.total) }"
                ></span>
                <span
                  class="in-progress"
                  :style="{ width: segmentWidth(chapter.in_progress, chapter.total) }"
                ></span>
                <span
                  class="not-started"
                  :style="{ width: segmentWidth(chapter.not_started, chapter.total) }"
                ></span>
              </div>
              <div class="chapter-counts">
                <span>已掌握 {{ chapter.mastered }}</span>
                <span>学习中 {{ chapter.in_progress }}</span>
                <span>未开始 {{ chapter.not_started }}</span>
              </div>
            </div>
          </div>
          <el-empty v-else description="暂无知识点数据" />
        </el-card>

        <div class="side-column">
          <el-card class="recommend-card" shadow="never">
            <template #header>
              <div class="card-title">
                <span><el-icon><Aim /></el-icon> 推荐下一步</span>
              </div>
            </template>
            <template v-if="dashboard.recommendation">
              <el-tag :type="dashboard.recommendation.status === 'in_progress' ? 'warning' : 'info'">
                {{ statusLabel(dashboard.recommendation.status) }}
              </el-tag>
              <h3>{{ dashboard.recommendation.name }}</h3>
              <p>{{ dashboard.recommendation.reason }}</p>
              <el-button type="primary" @click="goToPlan(dashboard.recommendation)">
                生成对应学习计划
              </el-button>
            </template>
            <div v-else class="all-mastered">
              <el-icon :size="36" color="#67c23a"><CircleCheckFilled /></el-icon>
              <h3>当前知识点已全部掌握</h3>
              <p>可以前往错题本继续巩固。</p>
            </div>
          </el-card>

          <el-card class="mistake-card" shadow="never">
            <template #header>
              <div class="card-title">
                <span><el-icon><WarningFilled /></el-icon> 错题统计</span>
                <el-button link type="primary" @click="router.push('/mistakes')">进入错题本</el-button>
              </div>
            </template>
            <div class="mistake-grid">
              <div><strong>{{ dashboard.mistake_summary.unresolved }}</strong><span>待复习</span></div>
              <div><strong>{{ dashboard.mistake_summary.resolved }}</strong><span>已复习</span></div>
              <div><strong>{{ dashboard.mistake_summary.wrong_attempts }}</strong><span>累计做错</span></div>
            </div>
          </el-card>
        </div>
      </section>

      <el-card class="recent-card" shadow="never">
        <template #header>
          <div class="card-title">
            <span><el-icon><Clock /></el-icon> 近期学习</span>
            <small>按最近活动时间排序</small>
          </div>
        </template>
        <div v-if="dashboard.recent.length" class="recent-list">
          <button
            v-for="node in dashboard.recent"
            :key="node.id"
            type="button"
            class="recent-item"
            @click="openKnowledge(node.id)"
          >
            <span class="recent-status" :style="{ background: statusColor(node.status) }"></span>
            <span class="recent-copy">
              <strong>{{ node.name || node.id }}</strong>
              <small>{{ formatActivity(node.last_activity_at || node.updated_at) }}</small>
            </span>
            <el-progress :percentage="node.mastery" :show-text="false" :stroke-width="6" />
            <b>{{ node.mastery }}%</b>
          </button>
        </div>
        <el-empty v-else description="还没有学习记录，从推荐知识点开始吧" :image-size="80" />
      </el-card>

    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Aim,
  CircleCheckFilled,
  Clock,
  Guide,
  Histogram,
  Share,
  WarningFilled
} from '@element-plus/icons-vue'
import { getLearnerDashboard, learnerErrorMessage } from '@/api/learner'
import { LEARNING_STATUS_META } from '@/utils/learningDashboard'

const router = useRouter()
const loading = ref(false)
const loadError = ref('')
const dashboard = ref({
  summary: { total: 0, mastered: 0, in_progress: 0, not_started: 0, mastery_percent: 0 },
  chapter_progress: [],
  mistake_summary: { unresolved: 0, resolved: 0, wrong_attempts: 0 },
  recent: [],
  recommendation: null
})

const statusCards = computed(() => [
  { key: 'mastered', ...LEARNING_STATUS_META.mastered, value: dashboard.value.summary.mastered },
  { key: 'in_progress', ...LEARNING_STATUS_META.in_progress, value: dashboard.value.summary.in_progress },
  { key: 'not_started', ...LEARNING_STATUS_META.not_started, value: dashboard.value.summary.not_started }
])

function statusPercent(value) {
  const total = dashboard.value.summary.total
  return total ? Math.round(value / total * 100) : 0
}

function statusLabel(status) {
  return LEARNING_STATUS_META[status]?.label || status
}

function statusColor(status) {
  return LEARNING_STATUS_META[status]?.color || '#c0c4cc'
}

function segmentWidth(value, total) {
  return total ? `${value / total * 100}%` : '0%'
}

function chapterBarTitle(chapter) {
  return `已掌握 ${chapter.mastered}，学习中 ${chapter.in_progress}，未开始 ${chapter.not_started}`
}

function formatActivity(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}

function openKnowledge(nodeId) {
  router.push({ path: '/knowledge', query: { focus: nodeId } })
}

function goToPlan(recommendation) {
  if (!recommendation) {
    router.push('/path')
    return
  }
  router.push({ path: '/path', query: { target: recommendation.id, auto: '1' } })
}

async function loadDashboard() {
  loading.value = true
  loadError.value = ''
  try {
    dashboard.value = await getLearnerDashboard()
  } catch (error) {
    console.error('加载学习总览失败:', error)
    loadError.value = learnerErrorMessage(error, '学习总览加载失败，请确认服务已启动。')
  } finally {
    loading.value = false
  }
}

onMounted(loadDashboard)
</script>

<style scoped>
.dashboard-page {
  max-width: 1320px;
  min-height: calc(100vh - 180px);
  margin: 0 auto;
  padding: 4px 0 28px;
}

.dashboard-header,
.card-title,
.chapter-heading,
.header-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.dashboard-header {
  margin-bottom: 20px;
}

.dashboard-header h1 {
  margin: 0 0 6px;
  color: #303133;
  font-size: 28px;
}

.dashboard-header p,
.mastery-copy p,
.recommend-card p,
.all-mastered p {
  margin: 0;
  color: #909399;
  line-height: 1.6;
}

.load-alert {
  margin-bottom: 20px;
}

.overview-grid {
  display: grid;
  grid-template-columns: minmax(360px, 1.7fr) repeat(3, minmax(150px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.mastery-content {
  display: flex;
  align-items: center;
  gap: 20px;
}

.mastery-card :deep(.el-progress__text) {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.mastery-card :deep(.el-progress__text strong) {
  color: #303133;
  font-size: 26px;
}

.mastery-card :deep(.el-progress__text span) {
  color: #909399;
  font-size: 12px;
}

.mastery-copy {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.eyebrow {
  color: #409eff;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.mastery-copy strong {
  color: #303133;
  font-size: 22px;
}

.status-card {
  position: relative;
  overflow: hidden;
}

.status-card::after {
  position: absolute;
  right: -24px;
  bottom: -30px;
  width: 96px;
  height: 96px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--status-color) 12%, transparent);
  content: '';
}

.status-dot {
  display: block;
  width: 10px;
  height: 10px;
  margin-bottom: 18px;
  border-radius: 50%;
  background: var(--status-color);
}

.status-value {
  color: #303133;
  font-size: 30px;
  font-weight: 700;
}

.status-label {
  margin-top: 5px;
  color: #606266;
}

.status-percent {
  margin-top: 14px;
  color: var(--status-color);
  font-size: 13px;
  font-weight: 600;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(300px, 0.85fr);
  gap: 16px;
  margin-bottom: 16px;
}

.card-title span {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #303133;
  font-weight: 600;
}

.card-title small {
  color: #909399;
  font-weight: 400;
}

.chapter-list {
  max-height: 520px;
  overflow-y: auto;
  padding-right: 6px;
}

.chapter-row + .chapter-row {
  margin-top: 22px;
}

.chapter-heading div {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.chapter-heading strong {
  color: #303133;
  font-size: 14px;
}

.chapter-heading span,
.chapter-counts {
  color: #909399;
  font-size: 12px;
}

.chapter-heading b {
  color: #409eff;
  font-size: 14px;
}

.status-bar {
  display: flex;
  height: 10px;
  margin: 9px 0 7px;
  overflow: hidden;
  border-radius: 999px;
  background: #ebeef5;
}

.status-bar span {
  height: 100%;
}

.status-bar .mastered { background: #67c23a; }
.status-bar .in-progress { background: #e6a23c; }
.status-bar .not-started { background: #c0c4cc; }

.chapter-counts {
  display: flex;
  gap: 18px;
}

.side-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.recommend-card h3,
.all-mastered h3 {
  margin: 14px 0 6px;
  color: #303133;
  font-size: 20px;
}

.recommend-card .el-button {
  width: 100%;
  margin-top: 18px;
}

.all-mastered {
  text-align: center;
}

.mistake-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  text-align: center;
}

.mistake-grid div + div {
  border-left: 1px solid #ebeef5;
}

.mistake-grid strong,
.mistake-grid span {
  display: block;
}

.mistake-grid strong {
  color: #303133;
  font-size: 24px;
}

.mistake-grid span {
  margin-top: 5px;
  color: #909399;
  font-size: 12px;
}

.recent-card {
  margin-bottom: 16px;
}

.recent-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
}

.recent-item {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) 100px 38px;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.recent-item:hover {
  border-color: #409eff;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.1);
}

.recent-status {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.recent-copy {
  min-width: 0;
}

.recent-copy strong,
.recent-copy small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-copy strong {
  color: #303133;
}

.recent-copy small {
  margin-top: 4px;
  color: #909399;
}

.recent-item > b {
  color: #606266;
  font-size: 13px;
  text-align: right;
}

.privacy-note {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  color: #909399;
  font-size: 12px;
}

@media (max-width: 1050px) {
  .overview-grid {
    grid-template-columns: repeat(3, 1fr);
  }

  .mastery-card {
    grid-column: 1 / -1;
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .dashboard-header,
  .mastery-content {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-actions {
    width: 100%;
  }

  .header-actions .el-button {
    flex: 1;
    margin-left: 0;
  }

  .overview-grid {
    grid-template-columns: 1fr;
  }

  .mastery-card {
    grid-column: auto;
  }

  .recent-list {
    grid-template-columns: 1fr;
  }

  .recent-item {
    grid-template-columns: 10px minmax(0, 1fr) 70px 36px;
  }
}
</style>
