<template>
  <div class="knowledge-page">
    <el-row :gutter="20">
      <!-- 左侧：知识点列表 -->
      <el-col :xs="24" :sm="24" :md="7" class="knowledge-list-column">
        <KnowledgeListPanel
          :items="knowledgePoints"
          :chapters="chapters"
          :selected-id="selectedKnowledge?.id || ''"
          :chapter-id="filterChapter"
          :knowledge-type="filterType"
          :keyword="searchKeyword"
          :loading="loading"
          :page="pagination.page"
          :page-size="pagination.pageSize"
          :total="pagination.total"
          @select="selectKnowledgePoint"
          @page-change="handlePageChange"
          @update:chapter-id="handleChapterChange"
          @update:knowledge-type="handleTypeChange"
          @update:keyword="handleSearch"
        />
      </el-col>

      <!-- 右侧：知识点详情 -->
      <el-col :xs="24" :sm="24" :md="17" class="knowledge-detail-column">
        <el-card v-if="selectedKnowledge" class="knowledge-detail-card">
          <template #header>
            <div class="card-header">
              <div class="detail-title">
                <el-tag :type="getTypeTagColor(selectedKnowledge.node_type)" size="large">
                  {{ selectedKnowledge.node_type || '知识点' }}
                </el-tag>
                <h2>{{ selectedKnowledge.name }}</h2>
              </div>
              <div class="header-actions">
                <el-button size="small" type="primary" @click="jumpToGraph">
                  <el-icon><Connection /></el-icon>
                  在图谱中查看
                </el-button>
              </div>
            </div>
          </template>

          <div ref="detailContentRef" v-loading="detailLoading" class="detail-content">
            <!-- 基本信息 -->
            <div class="info-meta">
              <span v-if="selectedKnowledge.node_id" class="meta-item">
                <el-icon><Ticket /></el-icon>
                ID: {{ selectedKnowledge.node_id }}
              </span>
              <span v-if="chapterInfo" class="meta-item">
                <el-icon><Collection /></el-icon>
                {{ chapterInfo.chapter_title }}
              </span>
              <span v-if="selectedKnowledge.section" class="meta-item">
                <el-icon><Document /></el-icon>
                {{ selectedKnowledge.section }}
              </span>
              <span class="meta-item mistake-count">
                <el-icon><CircleClose /></el-icon>
                <el-button link type="danger" size="small" @click="goToRelatedMistakes">
                  待复习错题：{{ relatedMistakeCount }}
                </el-button>
              </span>
            </div>

            <!-- 标签 -->
            <div v-if="validTags.length" class="tags-section">
              <el-tag
                v-for="tag in validTags"
                :key="tag"
                size="small"
                type="info"
                effect="plain"
                class="tag-item"
              >
                {{ tag }}
              </el-tag>
            </div>

            <!-- 核心概述 -->
            <div v-if="selectedKnowledge.overview" class="info-section highlight-section">
              <h3><el-icon><Star /></el-icon> 核心概述</h3>
              <p class="overview-text">{{ selectedKnowledge.overview }}</p>
            </div>

            <!-- 原文引述 -->
            <div v-if="selectedKnowledge.quote" class="info-section quote-section">
              <h3><el-icon><Reading /></el-icon> 原文引述</h3>
              <div class="quote-text md-content" v-html="formatQuote(selectedKnowledge.quote)"></div>
            </div>

            <!-- 知识详解 -->
            <div v-if="selectedKnowledge.elaboration" class="info-section">
              <h3><el-icon><Document /></el-icon> 知识详解</h3>
              <div class="elaboration-text md-content" v-html="formatMarkdown(selectedKnowledge.elaboration)"></div>
            </div>

            <!-- 子章节 -->
            <div v-if="hasSubSections" class="info-section">
              <h3><el-icon><List /></el-icon> 知识要点</h3>
              <el-collapse accordion>
                <el-collapse-item
                  v-for="(content, title) in subSectionsList"
                  :key="title"
                  :title="title"
                  :name="title"
                >
                  <div class="sub-section-content md-content" v-html="formatMarkdown(content)"></div>
                </el-collapse-item>
              </el-collapse>
            </div>

            <!-- 典型应用 -->
            <div v-if="selectedKnowledge.applications" class="info-section app-section">
              <h3><el-icon><Cpu /></el-icon> 典型应用</h3>
              <div class="app-text md-content" v-html="formatMarkdown(selectedKnowledge.applications)"></div>
            </div>

            <!-- 学习建议 -->
            <div v-if="selectedKnowledge.learning_tips" class="info-section tips-section">
              <h3><el-icon><Opportunity /></el-icon> 学习建议</h3>
              <div class="tips-text md-content" v-html="formatMarkdown(selectedKnowledge.learning_tips)"></div>
            </div>

            <!-- 思考题 -->
            <div v-if="selectedKnowledge.questions" class="info-section question-section">
              <h3><el-icon><QuestionFilled /></el-icon> 思考题</h3>
              <div class="questions-text md-content" v-html="formatMarkdown(selectedKnowledge.questions)"></div>
            </div>

            <!-- 实践练习 -->
            <div v-if="selectedKnowledge.exercises" class="info-section exercise-section">
              <h3><el-icon><Edit /></el-icon> 实践练习</h3>
              <div class="exercises-text md-content" v-html="formatMarkdown(selectedKnowledge.exercises)"></div>
            </div>

            <!-- 相关节点 -->
            <div v-if="relatedNodes && relatedNodes.length > 0" class="info-section related-section">
              <h3><el-icon><Share /></el-icon> 相关节点 ({{ relatedNodes.length }})</h3>
              <div class="related-nodes">
                <div
                  v-for="node in groupedRelatedNodes"
                  :key="node.type"
                  class="related-group"
                >
                  <div class="group-title">{{ getRelationLabel(node.type) }}</div>
                  <div class="group-items">
                    <el-tag
                      v-for="item in node.items"
                      :key="item.id"
                      class="related-tag"
                      @click="navigateToNode(item.id)"
                    >
                      {{ item.name }}
                    </el-tag>
                  </div>
                </div>
              </div>
            </div>

            <!-- 跨课程先修关系 -->
            <div v-if="crossCourseRelatedNodes.length" class="info-section cross-course-section">
              <h3><el-icon><Connection /></el-icon> 跨课程先修 ({{ crossCourseRelatedNodes.length }})</h3>
              <div class="cross-course-list">
                <el-tag
                  v-for="item in crossCourseRelatedNodes"
                  :key="item.id"
                  type="warning"
                  effect="plain"
                  class="cross-course-item"
                  @click="navigateToNode(item.id)"
                >
                  {{ item.name }}
                  <span class="cross-course-target">{{ courseForChapter(item.chapter_order) }}</span>
                </el-tag>
              </div>
            </div>

            <!-- 关联题目 -->
            <div v-if="relatedQuestions && relatedQuestions.length > 0" class="info-section questions-section">
              <h3><el-icon><Trophy /></el-icon> 关联题目 ({{ relatedQuestions.length }})</h3>
              <div class="questions-list">
                <div
                  v-for="q in relatedQuestions"
                  :key="q.id"
                  class="question-item"
                  @click="showQuestionDetail(q)"
                >
                  <div class="question-header">
                    <span class="question-id">{{ q.id }}</span>
                    <el-tag size="small" type="info" effect="plain" class="source-tag">码蹄集</el-tag>
                    <span
                      class="question-difficulty"
                      :style="{ color: getDifficultyColor(q.difficulty) }"
                    >
                      {{ q.difficulty }}
                    </span>
                  </div>
                  <div class="question-name">{{ q.name }}</div>
                  <div v-if="q.category" class="question-category">{{ q.category }}</div>
                </div>
              </div>
              <div class="questions-source">
                <span>来源：码蹄集</span>
              </div>
            </div>

            <!-- 关联节点章节 -->
            <div v-if="selectedKnowledge.related_section" class="info-section">
              <h3><el-icon><Link /></el-icon> 关联节点</h3>
              <div class="related-section-text md-content" v-html="formatRelatedSection(selectedKnowledge.related_section)"></div>
            </div>
          </div>
        </el-card>

        <el-card v-else class="welcome-card">
          <el-empty description="请从左侧选择一个知识点查看详情">
            <el-button type="primary" @click="loadAllKnowledgePoints">
              加载所有知识点
            </el-button>
          </el-empty>
        </el-card>
      </el-col>
    </el-row>

    <!-- 题目详情对话框 -->
    <el-dialog
      v-model="questionDialogVisible"
      :title="selectedQuestion ? selectedQuestion.name : ''"
      width="700px"
      destroy-on-close
    >
      <div v-if="selectedQuestion" v-loading="questionDetailLoading" class="question-detail">
        <!-- 基本信息 -->
        <div class="detail-section">
          <div class="detail-row">
            <span class="detail-label">题号：</span>
            <span class="detail-value">{{ selectedQuestion.id }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">来源：</span>
            <span class="detail-value"><el-tag size="small" type="info">码蹄集</el-tag></span>
          </div>
          <div class="detail-row">
            <span class="detail-label">难度：</span>
            <span class="detail-value" :style="{ color: getDifficultyColor(selectedQuestion.difficulty) }">
              {{ selectedQuestion.difficulty }}
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-label">分类：</span>
            <span class="detail-value">{{ selectedQuestion.category1 }} - {{ selectedQuestion.category2 }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">通过率：</span>
            <span class="detail-value">{{ selectedQuestion.pass_rate || '-' }}%</span>
          </div>
        </div>

        <!-- 题目描述 -->
        <div v-if="selectedQuestion.description" class="detail-section">
          <h4>题目描述</h4>
          <div class="detail-content" v-html="renderQuestionText(selectedQuestion.description)"></div>
        </div>

        <!-- 输入格式 -->
        <div v-if="selectedQuestion.input_format" class="detail-section">
          <h4>输入格式</h4>
          <div class="detail-content" v-html="renderQuestionText(selectedQuestion.input_format)"></div>
        </div>

        <!-- 输出格式 -->
        <div v-if="selectedQuestion.output_format" class="detail-section">
          <h4>输出格式</h4>
          <div class="detail-content" v-html="renderQuestionText(selectedQuestion.output_format)"></div>
        </div>

        <!-- 样例 -->
        <div v-if="selectedQuestion.sample_input || selectedQuestion.sample_output" class="detail-section">
          <h4>样例</h4>
          <div class="sample-box">
            <div v-if="selectedQuestion.sample_input" class="sample-item">
              <span class="sample-label">输入：</span>
              <pre class="sample-code">{{ selectedQuestion.sample_input }}</pre>
            </div>
            <div v-if="selectedQuestion.sample_output" class="sample-item">
              <span class="sample-label">输出：</span>
              <pre class="sample-code">{{ selectedQuestion.sample_output }}</pre>
            </div>
          </div>
        </div>

        <!-- 备注 -->
        <div v-if="selectedQuestion.remark" class="detail-section">
          <h4>备注</h4>
          <div class="detail-content" v-html="renderQuestionText(selectedQuestion.remark)"></div>
        </div>

        <!-- 关联知识点 -->
        <div v-if="questionKnowledgePoints.length > 0" class="detail-section">
          <h4>关联知识点</h4>
          <div class="knowledge-tags">
            <el-tag
              v-for="kp in questionKnowledgePoints"
              :key="kp.node_id"
              class="knowledge-tag"
              type="primary"
            >
              {{ kp.name }}
            </el-tag>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="detail-actions">
          <QuestionAttemptActions
            :question-id="selectedQuestion.id"
            :knowledge-points="questionKnowledgePoints"
            :disabled="questionDetailLoading"
            @recorded="refreshRelatedMistakeCount"
          />
          <el-button type="primary" @click="openQuestionUrl(selectedQuestion.url)">
            前往码蹄集做题
          </el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { 
  getKnowledgePoints, 
  getKnowledgePointPage,
  getKnowledgePointDetail,
  getQuestionsByKnowledge,
  getQuestionDetail
} from '@/api/graph'
import KnowledgeListPanel from '@/components/knowledge/KnowledgeListPanel.vue'
import QuestionAttemptActions from '@/components/learning/QuestionAttemptActions.vue'
import { useSafeMarkdown } from '@/composables/useSafeMarkdown'
import { getMistakes, loadLearningState } from '@/stores/progress'
import { getNodeTypeTagType } from '@/utils/nodeTypes'
import { 
  Connection, List, Document, Star, Reading,
  Cpu, Opportunity, QuestionFilled, Edit, Share, Link,
  Ticket, Collection, Trophy, CircleClose
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const {
  renderMarkdown: formatMarkdown,
  renderMarkdownInline: formatQuote,
  renderRelatedSection: formatRelatedSection,
  renderQuestionText
} = useSafeMarkdown()

// 数据状态
const knowledgePoints = ref([])
const selectedKnowledge = ref(null)
const relatedNodes = ref([])
const chapterInfo = ref(null)
const searchKeyword = ref('')
const filterType = ref('')
const filterChapter = ref('')
const loading = ref(false)
const detailLoading = ref(false)
const detailContentRef = ref(null)
const relatedQuestions = ref([])
const relatedMistakeCount = ref(0)
const pagination = ref({ page: 1, pageSize: 30, total: 0 })
let listController = null
let listRequestId = 0
let searchTimer = null

// 题目详情弹窗
const questionDialogVisible = ref(false)
const selectedQuestion = ref(null)
const questionKnowledgePoints = ref([])
const questionDetailLoading = ref(false)

// 章节列表（从后端动态加载，自动包含新增章节）
const chapters = ref([])

// 计算属性
// 分组相关节点
const groupedRelatedNodes = computed(() => {
  if (!relatedNodes.value || relatedNodes.value.length === 0) return []
  
  const groups = {}
  for (const node of relatedNodes.value) {
    const type = node.relation_type || 'RELATED_TO'
    if (!groups[type]) {
      groups[type] = []
    }
    groups[type].push(node)
  }
  
  return Object.entries(groups).map(([type, items]) => ({
    type,
    items
  }))
})

const crossCourseRelatedNodes = computed(() => {
  const currentOrder = Number(chapterInfo.value?.chapter_order)
  if (!Number.isInteger(currentOrder)) return []
  const currentCourse = currentOrder <= 12 ? 'data-structures' : 'algorithms'
  return (relatedNodes.value || []).filter(node => {
    if (node.relation_type !== 'PREREQUISITE') return false
    const targetOrder = Number(node.chapter_order)
    if (!Number.isInteger(targetOrder)) return false
    const targetCourse = targetOrder <= 12 ? 'data-structures' : 'algorithms'
    return targetCourse !== currentCourse
  })
})

// 把可能是 JSON 字符串的字段安全解析为对象/数组（导入时列表/字典被存成了字符串）
function parseMaybeJson(val) {
  if (typeof val === 'string') {
    try { return JSON.parse(val) } catch { return null }
  }
  return val
}

// 检查是否有有效的子章节
const hasSubSections = computed(() => {
  const sub = parseMaybeJson(selectedKnowledge.value?.sub_sections)
  return sub && typeof sub === 'object' && !Array.isArray(sub) && Object.keys(sub).length > 0
})

// 获取子章节列表（确保是对象）
const subSectionsList = computed(() => {
  const sub = parseMaybeJson(selectedKnowledge.value?.sub_sections)
  if (sub && typeof sub === 'object' && !Array.isArray(sub)) {
    return sub
  }
  return {}
})

// 获取有效标签列表
const validTags = computed(() => {
  const tags = parseMaybeJson(selectedKnowledge.value?.tags)
  if (Array.isArray(tags)) {
    return tags.filter(tag => tag && typeof tag === 'string' && tag.trim())
  }
  return []
})

// 获取类型标签颜色
function getTypeTagColor(type) {
  return getNodeTypeTagType(type)
}

// 获取关系类型标签
function getRelationLabel(type) {
  const labels = {
    'PREREQUISITE': '前置知识',
    'HAS_CORE_RELATION': '核心关联',
    'APPLIED_IN': '应用场景',
    'HAS_INSTANCE': '实例',
    'HAS_CORE_CONCEPT': '核心概念',
    'RELATED_TO': '相关节点'
  }
  return labels[type] || type
}

function courseForChapter(order) {
  const chapterOrder = Number(order)
  if (!Number.isInteger(chapterOrder)) return '未知课程'
  return chapterOrder <= 12 ? '数据结构' : '算法设计'
}

// 加载章节列表（动态，按 order 排序）
async function loadChapters() {
  try {
    const res = await getKnowledgePoints(100, 'Chapter')
    if (res.success && Array.isArray(res.data)) {
      chapters.value = res.data
        .filter(ch => ch.order != null)
        .sort((a, b) => a.order - b.order)
        .map(ch => ({
          id: ch.order,
          business_id: ch.id,
          name: ch.title || ch.name,
          source_name: ch.name,
          course_id: ch.order <= 12 ? 'data-structures' : 'algorithms',
          course_name: ch.order <= 12 ? '数据结构' : '算法设计'
        }))
    }
  } catch (error) {
    console.error('加载章节列表失败:', error)
  }
}

// 分页加载知识点摘要
async function loadAllKnowledgePoints() {
  listController?.abort()
  listController = new AbortController()
  const controller = listController
  const requestId = ++listRequestId
  loading.value = true
  try {
    const res = await getKnowledgePointPage({
      page: pagination.value.page,
      page_size: pagination.value.pageSize,
      chapter_id: filterChapter.value || null,
      knowledge_type: filterType.value || null,
      keyword: searchKeyword.value.trim() || null
    }, controller.signal)
    if (requestId !== listRequestId) return
    if (res.success && res.data) {
      knowledgePoints.value = res.data.items || []
      pagination.value.total = res.data.pagination?.total || 0
    } else {
      ElMessage.error('加载知识点失败')
    }
  } catch (error) {
    if (error.code === 'ERR_CANCELED') return
    console.error('加载知识点失败:', error)
    ElMessage.error('加载知识点失败')
  } finally {
    if (requestId === listRequestId) loading.value = false
  }
}

// 选择知识点
async function selectKnowledgePoint(kp) {
  selectedKnowledge.value = kp
  // 滚动详情区域到顶部
  await nextTick()
  if (detailContentRef.value) {
    detailContentRef.value.scrollTop = 0
  }
  await loadKnowledgeDetail(kp.id)
}

// 加载知识点详情
async function loadKnowledgeDetail(kpId) {
  detailLoading.value = true
  try {
    const res = await getKnowledgePointDetail(kpId)
    if (res.success && res.data) {
      selectedKnowledge.value = {
        ...selectedKnowledge.value,
        ...res.data.knowledge_point
      }
      relatedNodes.value = res.data.related_nodes || []
      chapterInfo.value = res.data.chapter_info || null
      refreshRelatedMistakeCount()
      
      // 加载关联题目
      loadRelatedQuestions(selectedKnowledge.value.name)
    }
  } catch (error) {
    console.error('加载知识点详情失败:', error)
    ElMessage.error('加载详情失败')
  } finally {
    detailLoading.value = false
  }
}

// 加载关联题目
async function loadRelatedQuestions(knowledgeName) {
  if (!knowledgeName) return
  try {
    const res = await getQuestionsByKnowledge(knowledgeName, 5)
    if (res.success && res.data) {
      relatedQuestions.value = res.data
    } else {
      relatedQuestions.value = []
    }
  } catch (error) {
    console.error('加载关联题目失败:', error)
    relatedQuestions.value = []
  }
}

// 显示题目详情
async function showQuestionDetail(q) {
  selectedQuestion.value = q
  questionKnowledgePoints.value = []
  questionDialogVisible.value = true
  questionDetailLoading.value = true

  try {
    const res = await getQuestionDetail(q.id)
    if (res && res.success && res.data) {
      selectedQuestion.value = {
        ...q,
        ...res.data.question
      }
      questionKnowledgePoints.value = res.data.knowledge_points || []
    }
  } catch (error) {
    console.error('加载题目详情失败:', error)
  } finally {
    questionDetailLoading.value = false
  }
}

function refreshRelatedMistakeCount() {
  const ids = new Set([
    selectedKnowledge.value?.id,
    selectedKnowledge.value?.node_id
  ].filter(Boolean).map(String))
  relatedMistakeCount.value = getMistakes().filter(record => (
    record.knowledge_ids.some(id => ids.has(String(id)))
  )).length
}

function goToRelatedMistakes() {
  const knowledgeId = selectedKnowledge.value?.node_id || selectedKnowledge.value?.id
  if (!knowledgeId) return
  router.push({ path: '/mistakes', query: { knowledge_id: knowledgeId } })
}

// 打开题目链接
function openQuestionUrl(url) {
  if (url) {
    window.open(url, '_blank')
  }
}

// 获取难度颜色
function getDifficultyColor(difficulty) {
  const colors = {
    '青铜': '#cd7f32',
    '白银': '#c0c0c0',
    '黄金': '#ffd700',
    '钻石': '#b9f2ff',
    '王者': '#ff6b6b'
  }
  return colors[difficulty] || '#909399'
}

// 章节筛选变化
function handleChapterChange(value) {
  filterChapter.value = value || ''
  pagination.value.page = 1
  loadAllKnowledgePoints()
}

// 类型筛选变化
function handleTypeChange(value) {
  filterType.value = value || ''
  pagination.value.page = 1
  loadAllKnowledgePoints()
}

// 搜索处理
function handleSearch(value) {
  searchKeyword.value = value || ''
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    pagination.value.page = 1
    loadAllKnowledgePoints()
  }, 300)
}

function handlePageChange(page) {
  pagination.value.page = page
  loadAllKnowledgePoints()
}

// 跳转到图谱
async function jumpToGraph() {
  if (!selectedKnowledge.value) return

  try {
    router.push({
      path: '/graph',
      query: { focus: selectedKnowledge.value.node_id || selectedKnowledge.value.name }
    })
  } catch (error) {
    console.error('跳转失败:', error)
    ElMessage.error('跳转失败，请稍后重试')
  }
}

// 导航到节点
async function navigateToNode(nodeId) {
  if (!nodeId) return false
  
  // 在当前列表中查找（支持 node_id 或 name）
  const node = knowledgePoints.value.find(kp => 
    kp.node_id === nodeId || kp.name === nodeId
  )
  
  if (node) {
    selectKnowledgePoint(node)
    return true
  }
  
  // 不在列表中，尝试通过 API 直接查询
  try {
    const res = await getKnowledgePointDetail(nodeId)
    if (res.success && res.data) {
      selectedKnowledge.value = res.data.knowledge_point
      relatedNodes.value = res.data.related_nodes || []
      chapterInfo.value = res.data.chapter_info || null
      refreshRelatedMistakeCount()
      loadRelatedQuestions(selectedKnowledge.value.name)
      return true
    }
  } catch (error) {
    console.error('查找知识点失败:', error)
  }
  
  return false
}

function getRouteQueryValue(value) {
  return Array.isArray(value) ? value[0] : value
}

async function navigateToChapterFromRoute() {
  const chapterParam = getRouteQueryValue(route.query.chapter_id || route.query.chapter)
  const sectionParam = getRouteQueryValue(route.query.section)
  if (chapterParam == null && !sectionParam) return false

  const chapter = chapters.value.find(ch => {
    const matchesId = chapterParam != null && (
      String(ch.id) === String(chapterParam) ||
      String(ch.business_id) === String(chapterParam)
    )
    const matchesName = sectionParam && (
      ch.name === sectionParam || ch.source_name === sectionParam
    )
    return matchesId || matchesName
  })

  if (!chapter) {
    ElMessage.warning('未找到对应章节')
    return true
  }

  filterChapter.value = chapter.id
  pagination.value.page = 1
  await loadAllKnowledgePoints()

  if (pagination.value.total > 0 && knowledgePoints.value.length > 0) {
    await selectKnowledgePoint(knowledgePoints.value[0])
    ElMessage.success(`已显示 ${chapter.name} 的 ${pagination.value.total} 个知识点`)
  } else {
    ElMessage.warning(`${chapter.name} 暂无关联知识点`)
  }
  return true
}

// 生命周期
onMounted(async () => {
  await Promise.all([loadAllKnowledgePoints(), loadChapters(), loadLearningState()])

  if (await navigateToChapterFromRoute()) return
  
  // 处理 URL 参数
  const focusParam = route.query.focus
  if (focusParam) {
    const found = await navigateToNode(getRouteQueryValue(focusParam))
    if (found) {
      ElMessage.success(`已定位到知识点: ${getRouteQueryValue(focusParam)}`)
    } else {
      ElMessage.warning(`未找到知识点: ${getRouteQueryValue(focusParam)}`)
    }
  }
})

onUnmounted(() => {
  clearTimeout(searchTimer)
  listController?.abort()
})
</script>

<style scoped>
.knowledge-page {
  padding: 20px;
  height: calc(100vh - 140px);
  overflow: hidden;
}

.knowledge-list-card,
.knowledge-detail-card,
.welcome-card {
  height: 100%;
  max-height: calc(100vh - 140px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.knowledge-list-card :deep(.el-card__body),
.knowledge-detail-card :deep(.el-card__body) {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 15px;
}

.knowledge-list-card :deep(.el-card__header) {
  padding: 15px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
}

.header-controls {
  width: 100%;
  display: flex;
  flex-direction: column;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.knowledge-list {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 10px;
  max-height: calc(100vh - 350px);
}

.knowledge-item {
  padding: 12px;
  margin-bottom: 8px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.knowledge-item:hover {
  border-color: #409eff;
  background-color: #f5f7fa;
  transform: translateX(4px);
}

.knowledge-item.active {
  border-color: #409eff;
  background: linear-gradient(135deg, #ecf5ff 0%, #f0f7ff 100%);
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
}

.kp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.kp-id {
  font-size: 12px;
  color: #909399;
  font-family: monospace;
}

.kp-name {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
  margin-bottom: 4px;
}

.kp-section {
  font-size: 12px;
  color: #909399;
}

.list-footer {
  padding: 10px;
  text-align: center;
  font-size: 12px;
  color: #909399;
  border-top: 1px solid #ebeef5;
}

.detail-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 10px 0;
  max-height: calc(100vh - 250px);
}

.detail-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-title h2 {
  margin: 0;
  font-size: 22px;
  color: #303133;
}

.info-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 8px;
  margin-bottom: 16px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #606266;
}

.tags-section {
  margin-bottom: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-item {
  margin: 0;
}

.info-section {
  margin: 12px 0;
  padding: 14px;
  background: #ffffff;
  border-radius: 8px;
  border-left: 4px solid #409eff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.info-section h3 {
  margin: 0 0 10px 0;
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e5e7eb;
}

.info-section h3 .el-icon {
  font-size: 16px;
  color: #409eff;
}

.highlight-section {
  background: #fffbeb;
  border-left-color: #f59e0b;
}

.highlight-section h3 .el-icon {
  color: #f59e0b;
}

.overview-text {
  font-size: 14px;
  line-height: 1.7;
  color: #1f2937;
  margin: 0;
}

.quote-section {
  background: #eff6ff;
  border-left-color: #3b82f6;
}

.quote-section h3 .el-icon {
  color: #3b82f6;
}

.quote-text {
  font-size: 14px;
  line-height: 1.6;
  color: #374151;
  font-style: italic;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 4px;
  border-left: 2px solid #93c5fd;
}

.elaboration-text,
.app-text,
.tips-text,
.questions-text,
.exercises-text,
.sub-section-content {
  font-size: 14px;
  line-height: 1.6;
  color: #374151;
  letter-spacing: 0;
  text-align: left;
}

/* ===== 富文本统一样式（针对 marked 标准输出 + KaTeX + highlight.js） ===== */

/* 普通段落 */
.md-content :deep(p) {
  margin: 6px 0;
  padding: 6px 10px;
  background: rgba(249, 250, 251, 0.8);
  border-radius: 3px;
  border-left: 2px solid #d1d5db;
}

/* 标题（数据源以 ###/#### 为主，统一收敛到正文层级） */
.md-content :deep(h1),
.md-content :deep(h2),
.md-content :deep(h3) {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  margin: 14px 0 6px 0;
  padding: 5px 8px;
  background: linear-gradient(90deg, #f3f4f6 0%, transparent 100%);
  border-left: 3px solid #6366f1;
  border-radius: 0 3px 3px 0;
}

.md-content :deep(h4) {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  margin: 12px 0 6px 0;
  padding: 5px 8px;
  background: linear-gradient(90deg, #f3f4f6 0%, transparent 100%);
  border-left: 3px solid #6366f1;
  border-radius: 0 3px 3px 0;
}

.md-content :deep(h5),
.md-content :deep(h6) {
  font-size: 13px;
  font-weight: 600;
  color: #4b5563;
  margin: 10px 0 5px 0;
  padding-left: 8px;
  border-left: 2px solid #9ca3af;
}

/* 列表 */
.md-content :deep(ul),
.md-content :deep(ol) {
  margin: 8px 0;
  padding-left: 0;
  list-style: none;
}

.md-content :deep(li) {
  margin: 3px 0;
  padding: 2px 6px;
  background: transparent;
  border-radius: 2px;
  position: relative;
  padding-left: 16px;
}

.md-content :deep(ul > li::before) {
  content: '•';
  position: absolute;
  left: 4px;
  color: #6366f1;
  font-weight: bold;
  font-size: 11px;
}

.md-content :deep(ol) {
  counter-reset: md-ol;
}

.md-content :deep(ol > li) {
  counter-increment: md-ol;
}

.md-content :deep(ol > li::before) {
  content: counter(md-ol) '.';
  position: absolute;
  left: 0;
  color: #6366f1;
  font-weight: 600;
  font-size: 13px;
}

/* 强调文本 */
.md-content :deep(strong) {
  color: #1f2937;
  font-weight: 600;
  background: transparent;
  padding: 0;
}

/* 行内代码（排除代码块内部的 code） */
.md-content :deep(code:not(.hljs)) {
  background: #fef3c7;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  color: #92400e;
  border: 1px solid #fcd34d;
}

/* 代码块（配色由 highlight.js 主题提供，这里只管布局） */
.md-content :deep(pre) {
  margin: 8px 0;
  border-radius: 5px;
  overflow: hidden;
  border: 1px solid #334155;
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.2);
}

.md-content :deep(pre code) {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
}

/* 表格 */
.md-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 13px;
  background: #fff;
  border-radius: 5px;
  overflow: hidden;
  border: 1px solid #e5e7eb;
}

.md-content :deep(thead) {
  background: #6366f1;
}

.md-content :deep(th) {
  padding: 8px 12px;
  text-align: left;
  font-weight: 600;
  color: #fff;
  border-bottom: none;
  white-space: nowrap;
}

.md-content :deep(td) {
  padding: 8px 12px;
  border-bottom: 1px solid #e5e7eb;
  color: #374151;
}

.md-content :deep(tbody tr:last-child td) {
  border-bottom: none;
}

.md-content :deep(tbody tr:hover),
.md-content :deep(tbody tr:nth-child(even)) {
  background: #f9fafb;
}

/* 引用块 */
.md-content :deep(blockquote) {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid #93c5fd;
  background: #eff6ff;
  border-radius: 0 3px 3px 0;
  color: #374151;
}

/* KaTeX 数学公式（配色/排版由 katex.css 提供，这里只管间距与滚动） */
.md-content :deep(.katex-display) {
  margin: 10px 0;
  padding: 10px 14px;
  background: #f0fdf4;
  border-left: 3px solid #22c55e;
  border-radius: 5px;
  overflow-x: auto;
  overflow-y: hidden;
}

.md-content :deep(.katex) {
  font-size: 1.05em;
}


.app-section {
  background: #ecfdf5;
  border-left-color: #10b981;
}

.app-section h3 .el-icon {
  color: #10b981;
}

.tips-section {
  background: #eff6ff;
  border-left-color: #2563eb;
}

.tips-section h3 .el-icon {
  color: #2563eb;
}

.question-section {
  background: #fdf2f8;
  border-left-color: #db2777;
}

.question-section h3 .el-icon {
  color: #db2777;
}

.exercise-section {
  background: #f5f3ff;
  border-left-color: #7c3aed;
}

.exercise-section h3 .el-icon {
  color: #7c3aed;
}

.related-section {
  background: #fffbeb;
  border-left-color: #d97706;
}

.related-section h3 .el-icon {
  color: #d97706;
}

.cross-course-section {
  background: #f0fdfa;
  border-left-color: #0f766e;
}

.cross-course-section h3 .el-icon {
  color: #0f766e;
}

.cross-course-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.cross-course-item {
  cursor: pointer;
}

.cross-course-target {
  margin-left: 6px;
  color: #0f766e;
  font-size: 12px;
}

.questions-section {
  background: #faf5ff;
  border-left-color: #a855f7;
}

.questions-section h3 .el-icon {
  color: #a855f7;
}

.questions-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.question-item {
  display: block;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 6px;
  border: 1px solid rgba(168, 85, 247, 0.15);
  text-decoration: none;
  transition: all 0.2s ease;
}

.question-item:hover {
  border-color: #a855f7;
  box-shadow: 0 2px 8px rgba(168, 85, 247, 0.15);
  transform: translateX(4px);
}

.question-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.question-id {
  font-size: 12px;
  font-family: monospace;
  color: #6b7280;
  background: #f3f4f6;
  padding: 1px 6px;
  border-radius: 3px;
}

.question-difficulty {
  font-size: 12px;
  font-weight: 600;
}

.question-name {
  font-size: 14px;
  font-weight: 500;
  color: #1f2937;
  margin-bottom: 2px;
}

.question-category {
  font-size: 12px;
  color: #9ca3af;
}

.source-tag {
  margin-left: auto;
  margin-right: 8px;
}

.questions-source {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed rgba(168, 85, 247, 0.2);
  font-size: 12px;
  color: #9ca3af;
  text-align: right;
}

.related-nodes {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.related-group {
  background: rgba(255, 255, 255, 0.9);
  padding: 8px 10px;
  border-radius: 5px;
  border: 1px solid rgba(217, 119, 6, 0.15);
}

.group-title {
  font-size: 13px;
  font-weight: 600;
  color: #92400e;
  margin-bottom: 6px;
  padding-left: 6px;
  border-left: 2px solid #d97706;
}

.group-items {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.related-tag {
  cursor: pointer;
  transition: background 0.15s ease;
  border-radius: 10px;
  padding: 2px 8px;
}

.related-tag:hover {
  background: #d97706;
  color: white;
}

.loading-state,
.empty-state {
  padding: 40px 0;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

/* 自定义滚动条样式 */
.knowledge-list::-webkit-scrollbar,
.detail-content::-webkit-scrollbar {
  width: 6px;
}

.knowledge-list::-webkit-scrollbar-track,
.detail-content::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.knowledge-list::-webkit-scrollbar-thumb,
.detail-content::-webkit-scrollbar-thumb {
  background: #c0c4cc;
  border-radius: 3px;
}

.knowledge-list::-webkit-scrollbar-thumb:hover,
.detail-content::-webkit-scrollbar-thumb:hover {
  background: #909399;
}

/* 折叠面板样式 */
:deep(.el-collapse) {
  border: none;
}

:deep(.el-collapse-item__header) {
  background: transparent;
  font-weight: 500;
  color: #303133;
  border-bottom: 1px solid #ebeef5;
}

:deep(.el-collapse-item__content) {
  padding: 12px 0;
}

/* 题目详情弹窗样式 */
.question-detail {
  max-height: 60vh;
  overflow-y: auto;
}

.detail-section {
  margin-bottom: 16px;
  padding: 12px;
  background: #f9fafb;
  border-radius: 6px;
}

.detail-section h4 {
  margin: 0 0 8px 0;
  font-size: 13px;
  color: #303133;
  padding-bottom: 6px;
  border-bottom: 1px solid #e5e7eb;
}

.detail-row {
  display: flex;
  margin-bottom: 6px;
}

.detail-row:last-child {
  margin-bottom: 0;
}

.detail-label {
  width: 60px;
  font-size: 13px;
  color: #909399;
}

.detail-value {
  flex: 1;
  font-size: 13px;
  color: #303133;
}

.detail-content {
  font-size: 13px;
  line-height: 1.6;
  color: #4b5563;
  white-space: pre-wrap;
}

.sample-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sample-item {
  display: flex;
  align-items: flex-start;
}

.sample-label {
  width: 45px;
  font-size: 12px;
  color: #606266;
  flex-shrink: 0;
}

.sample-code {
  flex: 1;
  margin: 0;
  padding: 8px;
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
  overflow-x: auto;
}

.knowledge-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.knowledge-tag {
  cursor: default;
}

.detail-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  justify-content: center;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
}

:deep(.el-dialog) {
  max-width: calc(100vw - 24px);
}

@media (max-width: 900px) {
  .knowledge-page {
    height: auto;
    min-height: calc(100vh - 144px);
    padding: 0;
    overflow: visible;
  }

  .knowledge-list-column,
  .knowledge-detail-column {
    max-width: 100%;
    flex: 0 0 100%;
  }

  .knowledge-detail-column {
    margin-top: 12px;
  }

  .knowledge-list-column :deep(.knowledge-list-card),
  .knowledge-detail-card,
  .welcome-card {
    height: auto;
    max-height: none;
  }

  .knowledge-list-column :deep(.knowledge-list) {
    max-height: 42vh;
  }

  .detail-content {
    max-height: none;
    overflow: visible;
  }

  .card-header,
  .detail-title,
  .info-meta,
  .detail-actions {
    align-items: flex-start;
    gap: 10px;
  }

  .detail-title {
    flex-wrap: wrap;
  }

  .detail-title h2 {
    font-size: 19px;
    overflow-wrap: anywhere;
  }

  .sample-item,
  .detail-row {
    flex-wrap: wrap;
  }
}
</style>
