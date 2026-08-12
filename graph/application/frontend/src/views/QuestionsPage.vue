<template>
  <div class="questions-page">
    <el-row :gutter="20">
      <!-- 左侧：筛选面板 -->
      <el-col :xs="24" :sm="24" :md="5" class="questions-filter-column">
        <el-card class="filter-card">
          <template #header>
            <div class="card-header">
              <span>题目筛选</span>
              <el-button text type="primary" size="small" @click="resetFilters">
                重置
              </el-button>
            </div>
          </template>

          <!-- 搜索 -->
          <div class="filter-section">
            <el-input
              v-model="searchKeyword"
              placeholder="搜索题目名称..."
              clearable
              size="small"
              @input="handleSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </div>

          <!-- 难度筛选 -->
          <div class="filter-section">
            <div class="filter-title">难度</div>
            <div class="filter-tags">
              <el-tag
                v-for="d in difficulties"
                :key="d.difficulty"
                :type="filterDifficulty === d.difficulty ? 'primary' : 'info'"
                :effect="filterDifficulty === d.difficulty ? 'dark' : 'plain'"
                class="filter-tag"
                @click="selectDifficulty(d.difficulty)"
              >
                {{ d.difficulty }} ({{ d.count }})
              </el-tag>
            </div>
          </div>

          <!-- 分类筛选 -->
          <div class="filter-section">
            <div class="filter-title">分类</div>
            <div class="filter-tags category-tags">
              <el-tag
                v-for="c in categories"
                :key="c.category"
                :type="filterCategory === c.category ? 'primary' : 'info'"
                :effect="filterCategory === c.category ? 'dark' : 'plain'"
                class="filter-tag"
                @click="selectCategory(c.category)"
              >
                {{ c.category }} ({{ c.count }})
              </el-tag>
            </div>
          </div>

          <!-- 排序 -->
          <div class="filter-section">
            <div class="filter-title">排序</div>
            <el-select v-model="sortBy" placeholder="选择排序" size="small" style="width: 100%" @change="handleFilterChange">
              <el-option label="按题号" value="id" />
              <el-option label="按难度" value="difficulty" />
              <el-option label="知识点数量" value="kp_count" />
            </el-select>
          </div>

          <!-- 统计信息 -->
          <div class="stats-section">
            <div class="stat-item">
              <span class="stat-label">总题目数</span>
              <span class="stat-value">{{ pagination.total }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">当前页</span>
              <span class="stat-value">{{ pagination.page }} / {{ pagination.total_pages || 1 }}</span>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：题目列表 -->
      <el-col :xs="24" :sm="24" :md="19" class="questions-list-column">
        <el-card class="questions-card">
          <template #header>
            <div class="card-header">
              <span>算法题目 ({{ pagination.total }} 道)</span>
              <div class="header-actions">
                <el-tag v-if="filterDifficulty" type="primary" closable @close="filterDifficulty = ''; handleFilterChange()">
                  {{ filterDifficulty }}
                </el-tag>
                <el-tag v-if="filterCategory" type="success" closable @close="filterCategory = ''; handleFilterChange()">
                  {{ filterCategory }}
                </el-tag>
              </div>
            </div>
          </template>

          <div v-loading="loading" class="questions-list">
            <div
              v-for="q in questions"
              :key="q.id"
              class="question-card"
              @click="showQuestionDetail(q)"
            >
              <div class="question-main">
                <div class="question-header">
                  <span class="question-id">{{ q.id }}</span>
                  <div class="question-badges">
                    <el-tag size="small" type="info" effect="plain" class="source-tag">码蹄集</el-tag>
                    <span class="question-difficulty" :style="{ color: getDifficultyColor(q.difficulty) }">
                      {{ q.difficulty }}
                    </span>
                  </div>
                </div>
                <div class="question-name">{{ q.name }}</div>
                <div class="question-footer">
                  <div class="question-category">
                    <el-tag size="small" type="info" effect="plain">{{ q.category1 }}</el-tag>
                    <el-tag v-if="q.category2" size="small" type="info" effect="plain">
                      {{ q.category2 }}
                    </el-tag>
                  </div>
                  <div class="kp-count" v-if="q.kp_count">
                    <el-icon><Connection /></el-icon>
                    {{ q.kp_count }} 个知识点
                  </div>
                </div>
              </div>
              <div class="question-actions">
                <el-button type="primary" size="small" link @click.stop="openQuestionUrl(q.url)">
                  前往做题
                </el-button>
              </div>
            </div>

            <el-empty v-if="!loading && questions.length === 0" description="暂无题目" />
          </div>

          <!-- 分页 -->
          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="currentPage"
              :page-size="pagination.page_size"
              :total="pagination.total"
              layout="total, prev, pager, next, jumper"
              @current-change="handlePageChange"
            />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 题目详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
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
          <div v-if="hasMissingFormula(selectedQuestion.description)" class="missing-formula-hint">
            <el-icon><PictureFilled /></el-icon>
            题目含公式图片，本地数据未保存，
            <el-button type="primary" link size="small" @click="openQuestionUrl(selectedQuestion.url)">查看原题</el-button>
          </div>
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
        <div v-if="relatedKnowledgePoints.length > 0" class="detail-section">
          <h4>关联知识点 ({{ relatedKnowledgePoints.length }})</h4>
          <div class="knowledge-tags">
            <el-tag
              v-for="kp in relatedKnowledgePoints"
              :key="kp.node_id"
              class="knowledge-tag"
              :type="kp.match_type === 'category' ? 'success' : 'primary'"
              @click="goToKnowledge(kp)"
            >
              {{ kp.name }}
            </el-tag>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="detail-actions">
          <QuestionAttemptActions
            :question-id="selectedQuestion.id"
            :knowledge-points="relatedKnowledgePoints"
            :disabled="questionDetailLoading"
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
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Connection, PictureFilled } from '@element-plus/icons-vue'
import { getQuestions, getQuestionCategories, getQuestionDetail } from '@/api/graph'
import { useSafeMarkdown } from '@/composables/useSafeMarkdown'
import { detectMissingFormula } from '@/utils/questionMathText'
import QuestionAttemptActions from '@/components/learning/QuestionAttemptActions.vue'

const { renderQuestionText } = useSafeMarkdown()
const hasMissingFormula = detectMissingFormula

const router = useRouter()
const route = useRoute()

// 数据状态
const questions = ref([])
const categories = ref([])
const difficulties = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pagination = ref({
  page: 1,
  page_size: 20,
  total: 0,
  total_pages: 0
})

// 筛选条件
const searchKeyword = ref('')
const filterDifficulty = ref('')
const filterCategory = ref('')
const sortBy = ref('id')
let searchTimer = null

// 详情对话框
const detailDialogVisible = ref(false)
const selectedQuestion = ref(null)
const relatedKnowledgePoints = ref([])
const questionDetailLoading = ref(false)

// 加载题目列表
async function loadQuestions() {
  loading.value = true
  try {
    const res = await getQuestions(
      currentPage.value,
      pagination.value.page_size,
      filterDifficulty.value || null,
      filterCategory.value || null,
      searchKeyword.value || null,
      sortBy.value
    )
    
    if (res && res.success && res.data) {
      questions.value = res.data.questions || []
      pagination.value = res.data.pagination
    }
  } catch (error) {
    console.error('加载题目失败:', error)
    ElMessage.error('加载题目失败')
  } finally {
    loading.value = false
  }
}

// 加载分类信息
async function loadCategories() {
  try {
    const res = await getQuestionCategories()
    if (res && res.success && res.data) {
      categories.value = res.data.categories || []
      difficulties.value = res.data.difficulties || []
    }
  } catch (error) {
    console.error('加载分类信息失败:', error)
  }
}

// 处理搜索
function handleSearch() {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
  searchTimer = setTimeout(() => {
    currentPage.value = 1
    loadQuestions()
  }, 300)
}

// 处理筛选变化
function handleFilterChange() {
  currentPage.value = 1
  loadQuestions()
}

// 处理分页变化
function handlePageChange(page) {
  currentPage.value = page
  loadQuestions()
}

// 选择难度
function selectDifficulty(difficulty) {
  if (filterDifficulty.value === difficulty) {
    filterDifficulty.value = ''
  } else {
    filterDifficulty.value = difficulty
  }
  handleFilterChange()
}

// 选择分类
function selectCategory(category) {
  if (filterCategory.value === category) {
    filterCategory.value = ''
  } else {
    filterCategory.value = category
  }
  handleFilterChange()
}

// 重置筛选
function resetFilters() {
  searchKeyword.value = ''
  filterDifficulty.value = ''
  filterCategory.value = ''
  sortBy.value = 'id'
  currentPage.value = 1
  loadQuestions()
}

// 显示题目详情
async function showQuestionDetail(q) {
  selectedQuestion.value = q
  relatedKnowledgePoints.value = []
  detailDialogVisible.value = true
  questionDetailLoading.value = true
  
  try {
    const res = await getQuestionDetail(q.id)
    if (res && res.success && res.data) {
      selectedQuestion.value = {
        ...q,
        ...res.data.question
      }
      relatedKnowledgePoints.value = res.data.knowledge_points || []
    }
  } catch (error) {
    console.error('加载题目详情失败:', error)
  } finally {
    questionDetailLoading.value = false
  }
}

// 打开题目链接
function openQuestionUrl(url) {
  if (url) {
    window.open(url, '_blank')
  }
}

// 跳转到知识点
function goToKnowledge(kp) {
  detailDialogVisible.value = false
  router.push({
    path: '/knowledge',
    query: { focus: kp.node_id || kp.name }
  })
}

// 获取难度颜色
function getDifficultyColor(difficulty) {
  const colors = {
    '青铜': '#cd7f32',
    '白银': '#a8a8a8',
    '黄金': '#ffd700',
    '钻石': '#b9f2ff',
    '王者': '#ff6b6b',
    '星耀': '#ff6b6b',
    '铂金': '#b9f2ff',
    '简单': '#67c23a',
    '中等': '#e6a23c',
    '困难': '#f56c6c'
  }
  return colors[difficulty] || '#909399'
}

// 从URL参数初始化筛选条件
function initFromUrl() {
  const query = route.query
  
  // 处理可能的数组情况（URL参数可能是数组）
  const getQueryParam = (param) => {
    const value = query[param]
    return Array.isArray(value) ? value[0] : value
  }
  
  const difficulty = getQueryParam('difficulty')
  const category1 = getQueryParam('category1')
  const keyword = getQueryParam('keyword')
  const sortByParam = getQueryParam('sort_by')
  const questionId = getQueryParam('id')
  
  if (difficulty) filterDifficulty.value = difficulty
  if (category1) filterCategory.value = category1
  if (keyword) searchKeyword.value = keyword
  if (sortByParam) sortBy.value = sortByParam
  
  // 返回 questionId 供后续处理
  return questionId
}

// 根据ID打开题目详情
async function openQuestionById(questionId) {
  selectedQuestion.value = { id: questionId, name: questionId }
  relatedKnowledgePoints.value = []
  detailDialogVisible.value = true
  questionDetailLoading.value = true
  try {
    const res = await getQuestionDetail(questionId)
    if (res && res.success && res.data) {
      selectedQuestion.value = res.data.question
      relatedKnowledgePoints.value = res.data.knowledge_points || []
    }
  } catch (error) {
    console.error('加载题目详情失败:', error)
  } finally {
    questionDetailLoading.value = false
  }
}

// 生命周期
onMounted(async () => {
  // 先加载分类信息
  await loadCategories()
  // 从URL初始化筛选条件，获取可能存在的题目ID
  const questionId = initFromUrl()
  // 最后加载题目
  await loadQuestions()
  // 如果URL指定了题目ID，打开详情
  if (questionId) {
    openQuestionById(questionId)
  }
})
</script>

<style scoped>
.questions-page {
  height: calc(100vh - 160px);
  background: #f5f7fa;
  display: flex;
  flex-direction: column;
}

.questions-page .el-row {
  height: 100%;
  flex: 1;
}

.questions-page .el-col {
  height: 100%;
}

.filter-card,
.questions-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.filter-card :deep(.el-card__body),
.questions-card :deep(.el-card__body) {
  flex: 1;
  overflow-y: auto;
  padding: 15px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.filter-section {
  margin-bottom: 20px;
}

.filter-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 10px;
}

.filter-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-tag {
  cursor: pointer;
  box-sizing: border-box;
  max-width: 100%;
  transition: color 0.2s, border-color 0.2s, background-color 0.2s, box-shadow 0.2s;
}

.filter-tag:hover {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-5);
  background-color: var(--el-color-primary-light-9);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-8);
}

.category-tags {
  max-height: 200px;
  overflow-y: auto;
}

.stats-section {
  padding: 15px;
  background: #f5f7fa;
  border-radius: 8px;
  margin-top: 20px;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.stat-item:last-child {
  margin-bottom: 0;
}

.stat-label {
  font-size: 13px;
  color: #909399;
}

.stat-value {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.questions-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
  padding: 10px;
}

.question-card {
  padding: 15px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.question-card:hover {
  border-color: #409eff;
  box-shadow: 0 2px 12px rgba(64, 158, 255, 0.15);
  transform: translateY(-2px);
}

.question-main {
  flex: 1;
  min-width: 0;
}

.question-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.question-id {
  font-size: 12px;
  font-family: monospace;
  color: #909399;
  background: #f5f7fa;
  padding: 2px 8px;
  border-radius: 3px;
}

.question-badges {
  display: flex;
  align-items: center;
  gap: 8px;
}

.question-difficulty {
  font-size: 12px;
  font-weight: 600;
}

.question-name {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.question-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.question-category {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.kp-count {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #909399;
}

.source-tag {
  margin-left: auto;
  margin-right: 8px;
}

.pagination-wrapper {
  padding: 15px;
  display: flex;
  justify-content: center;
  border-top: 1px solid #ebeef5;
}

/* 详情对话框样式 */
.question-detail {
  max-height: 60vh;
  overflow-y: auto;
}

.detail-section {
  margin-bottom: 20px;
  padding: 15px;
  background: #f9fafb;
  border-radius: 8px;
}

.detail-section h4 {
  margin: 0 0 10px 0;
  font-size: 14px;
  color: #303133;
  padding-bottom: 8px;
  border-bottom: 1px solid #e5e7eb;
}

.detail-row {
  display: flex;
  margin-bottom: 8px;
}

.detail-row:last-child {
  margin-bottom: 0;
}

.detail-label {
  width: 70px;
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
  gap: 10px;
}

.sample-item {
  display: flex;
  align-items: flex-start;
}

.sample-label {
  width: 50px;
  font-size: 13px;
  color: #606266;
  flex-shrink: 0;
}

.sample-code {
  flex: 1;
  margin: 0;
  padding: 10px;
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 5px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
  overflow-x: auto;
}

.knowledge-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.knowledge-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.knowledge-tag:hover {
  transform: scale(1.05);
}

.detail-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  justify-content: center;
  padding-top: 15px;
  border-top: 1px solid #e5e7eb;
}

/* 滚动条样式 */
.filter-card :deep(.el-card__body)::-webkit-scrollbar,
.questions-card :deep(.el-card__body)::-webkit-scrollbar,
.question-detail::-webkit-scrollbar {
  width: 6px;
}

.filter-card :deep(.el-card__body)::-webkit-scrollbar-track,
.questions-card :deep(.el-card__body)::-webkit-scrollbar-track,
.question-detail::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.filter-card :deep(.el-card__body)::-webkit-scrollbar-thumb,
.questions-card :deep(.el-card__body)::-webkit-scrollbar-thumb,
.question-detail::-webkit-scrollbar-thumb {
  background: #c0c4cc;
  border-radius: 3px;
}

.missing-formula-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  font-size: 12px;
  color: #9ca3af;
}

:deep(.el-dialog) {
  max-width: calc(100vw - 24px);
}

@media (max-width: 900px) {
  .questions-page {
    height: auto;
    min-height: calc(100vh - 144px);
  }

  .questions-page .el-row,
  .questions-page .el-col {
    height: auto;
  }

  .questions-filter-column,
  .questions-list-column {
    max-width: 100%;
    flex: 0 0 100%;
  }

  .questions-list-column {
    margin-top: 12px;
  }

  .filter-card,
  .questions-card {
    height: auto;
  }

  .category-tags {
    max-height: 140px;
  }

  .questions-list {
    grid-template-columns: minmax(0, 1fr);
    padding: 0;
  }

  .card-header,
  .question-card,
  .question-footer,
  .detail-row,
  .sample-item {
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 8px;
  }

  .question-actions {
    width: 100%;
    text-align: right;
  }

  .question-name {
    white-space: normal;
    overflow-wrap: anywhere;
  }

  .pagination-wrapper {
    overflow-x: auto;
    justify-content: flex-start;
  }

  .sample-code {
    min-width: 0;
    width: 100%;
  }
}
</style>
