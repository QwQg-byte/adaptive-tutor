<template>
  <div class="search-page">
    <el-row :gutter="20">
      <!-- 搜索区域 -->
      <el-col :span="24">
        <el-card class="search-card">
          <el-row :gutter="20" class="search-controls">
            <el-col :xs="24" :sm="16" :md="16" class="search-input-col">
              <el-input
                v-model="searchForm.keyword"
                placeholder="搜索知识点、章节、题目..."
                size="large"
                clearable
                @input="handleInput"
                @keyup.enter="handleSearch"
                ref="searchInput"
              >
                <template #prefix>
                  <el-icon><Search /></el-icon>
                </template>
              </el-input>
            </el-col>
            <el-col :xs="24" :sm="4" :md="4">
              <el-select v-model="searchForm.nodeType" placeholder="全部类型" clearable>
                <el-option
                  v-for="(label, key) in nodeTypeLabels"
                  :key="key"
                  :label="label"
                  :value="key"
                />
              </el-select>
            </el-col>
            <el-col :xs="24" :sm="4" :md="4">
              <el-button class="search-submit" type="primary" size="large" @click="handleSearch" :loading="loading">
                搜索
              </el-button>
            </el-col>
          </el-row>
        </el-card>
      </el-col>

      <!-- 搜索建议 - 使用 fixed 定位显示在顶层 -->
      <teleport to="body">
        <div
          v-if="suggestions.length > 0 && showSuggestions"
          class="suggestions"
          :style="suggestionsStyle"
        >
          <div
            v-for="item in suggestions"
            :key="item.label + item.type"
            class="suggestion-item"
            @click="selectSuggestion(item)"
          >
            <div class="suggestion-content">
              <span class="suggestion-name">
                <template v-for="(segment, index) in highlightSegments(item.label, searchForm.keyword)" :key="index">
                  <mark v-if="segment.matched" class="search-highlight">{{ segment.text }}</mark>
                  <span v-else>{{ segment.text }}</span>
                </template>
              </span>
              <span v-if="item.sub_type" class="suggestion-sub">{{ item.sub_type }}</span>
              <span v-if="item.section" class="suggestion-section">{{ item.section }}</span>
            </div>
            <el-tag size="small" :type="getNodeTypeTagColor(item.type)">{{ item.type }}</el-tag>
          </div>
        </div>
      </teleport>
    </el-row>

    <!-- 搜索结果 -->
    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>搜索结果 ({{ searchResults.length }})</span>
              <el-tag v-if="lastSearchKeyword">关键字: {{ lastSearchKeyword }}</el-tag>
            </div>
          </template>

          <el-empty v-if="!hasSearched" description="请输入关键词搜索知识点、章节或题目" />
          <el-empty v-else-if="searchResults.length === 0" description="未找到匹配的结果" />
          
          <div v-else class="results-container">
            <div
              v-for="row in searchResults"
              :key="row.id"
              class="result-card"
            >
              <div class="result-header">
                <el-tag :type="getNodeTypeTagColor(row.label)" effect="plain">
                  {{ row.label_cn || row.label }}
                </el-tag>
                <span class="result-id" v-if="row.node_id">{{ row.node_id }}</span>
                <el-tag
                  v-if="Number(row.search_score) > 0"
                  size="small"
                  type="warning"
                  effect="plain"
                  class="score-tag"
                >相关度 {{ formatSearchScore(row.search_score) }}</el-tag>
              </div>
              <div class="result-name" @click="showNodeDetail(row)">
                <template v-for="(segment, index) in highlightSegments(row.name, lastSearchKeyword)" :key="index">
                  <mark v-if="segment.matched" class="search-highlight">{{ segment.text }}</mark>
                  <span v-else>{{ segment.text }}</span>
                </template>
              </div>
              <div class="result-overview" v-if="row.overview">
                <template v-for="(segment, index) in highlightSegments(truncateText(row.overview, 100), lastSearchKeyword)" :key="index">
                  <mark v-if="segment.matched" class="search-highlight">{{ segment.text }}</mark>
                  <span v-else>{{ segment.text }}</span>
                </template>
              </div>
              <div class="result-meta">
                <span v-if="row.section"><el-icon><Folder /></el-icon> {{ row.section }}</span>
                <span v-if="row.difficulty"><el-icon><Star /></el-icon> {{ row.difficulty }}</span>
                <span v-if="row.category1"><el-icon><Collection /></el-icon> {{ row.category1 }}</span>
              </div>
              <div class="result-actions">
                <el-button type="primary" link size="small" @click="handleNodeAction(row)">
                  {{ getNodeActionButtonText(row.label) }}
                </el-button>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 节点详情对话框 -->
    <el-dialog v-model="showDetailDialog" :title="selectedNode.name" width="600px">
      <el-descriptions :column="2" border v-if="selectedNode">
        <el-descriptions-item label="类型">
          <el-tag :type="getNodeTypeTagColor(selectedNode.label)">
            {{ selectedNode.label_cn || selectedNode.label }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item
          v-for="[key, value] in detailProperties"
          :key="key" 
          :label="getSearchPropertyLabel(key)"
        >
          {{ formatValue(value) }}
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="showDetailDialog = false">关闭</el-button>
        <el-button type="primary" @click="handleNodeAction(selectedNode)">{{ getNodeActionButtonText(selectedNode.label) }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { searchByKeyword, getSearchSuggestions, getLabels } from '@/api/search'
import { ElMessage } from 'element-plus'
import { Search, Folder, Star, Collection } from '@element-plus/icons-vue'
import { NODE_TYPE_LABELS, getNodeTypeLabel, getNodeTypeTagType } from '@/utils/nodeTypes'
import { getSearchPropertyLabel } from '@/utils/searchFields'

const router = useRouter()

const searchForm = ref({
  keyword: '',
  nodeType: null
})

const nodeTypeLabels = ref({ ...NODE_TYPE_LABELS })

const suggestions = ref([])
const searchResults = ref([])
const lastSearchKeyword = ref('')
const loading = ref(false)
const hasSearched = ref(false)

const showDetailDialog = ref(false)
const selectedNode = ref({})
const detailProperties = computed(() => Object.entries(selectedNode.value).filter(
  ([key]) => !['name', 'label', 'label_cn', 'id', 'search_score'].includes(key)
))

const searchInput = ref(null)
const showSuggestions = ref(false)

let searchTimer = null
let suggestionController = null
let searchController = null

// 计算下拉框位置样式
const suggestionsStyle = computed(() => {
  if (!searchInput.value) {
    return {}
  }

  // 获取输入框的位置信息
  const inputElement = searchInput.value.$el || searchInput.value
  const rect = inputElement.getBoundingClientRect()

  return {
    position: 'fixed',
    top: `${rect.bottom + 4}px`,
    left: `${rect.left}px`,
    width: `${rect.width}px`,
    zIndex: 9999
  }
})

// 初始化
onMounted(async () => {
  try {
    const res = await getLabels()
    if (res.success && res.data) {
      // 构建类型映射
      const labels = {}
      res.data.forEach(label => {
        labels[label] = getNodeTypeLabel(label)
      })
      nodeTypeLabels.value = labels
    }
  } catch (error) {
    console.error('获取节点类型失败:', error)
  }
})

// 输入处理（防抖）
function handleInput() {
  if (searchForm.value.keyword.length >= 1) {
    clearTimeout(searchTimer)
    searchTimer = setTimeout(() => {
      loadSuggestions()
    }, 300)
  } else {
    suggestions.value = []
    showSuggestions.value = false
  }
}

// 加载搜索建议
async function loadSuggestions() {
  suggestionController?.abort()
  suggestionController = new AbortController()
  const keyword = searchForm.value.keyword
  try {
    const res = await getSearchSuggestions({
      keyword,
      limit: 10
    }, suggestionController.signal)
    if (res.success && keyword === searchForm.value.keyword) {
      suggestions.value = res.data
      showSuggestions.value = true
    }
  } catch (error) {
    if (error.code === 'ERR_CANCELED') return
    console.error('获取搜索建议失败:', error)
  }
}

// 选择建议
function selectSuggestion(item) {
  searchForm.value.keyword = item.label
  suggestions.value = []
  showSuggestions.value = false
  handleSearch()
}

// 搜索
async function handleSearch() {
  if (!searchForm.value.keyword) {
    ElMessage.warning('请输入搜索关键词')
    return
  }

  showSuggestions.value = false

  searchController?.abort()
  searchController = new AbortController()
  const controller = searchController
  const keyword = searchForm.value.keyword
  loading.value = true
  hasSearched.value = true

  try {
    const params = {
      keyword,
      limit: 100
    }

    if (searchForm.value.nodeType) {
      params.node_type = searchForm.value.nodeType
    }

    const res = await searchByKeyword(params, controller.signal)
    if (res.success && keyword === searchForm.value.keyword) {
      searchResults.value = res.data
      lastSearchKeyword.value = keyword
      ElMessage.success(`找到 ${res.data.length} 个结果`)
    }
  } catch (error) {
    if (error.code === 'ERR_CANCELED') return
    ElMessage.error('搜索失败')
    console.error(error)
  } finally {
    if (searchController === controller) loading.value = false
  }
}

onUnmounted(() => {
  clearTimeout(searchTimer)
  suggestionController?.abort()
  searchController?.abort()
  document.removeEventListener('click', handleDocumentClick)
})

// 显示节点详情
function showNodeDetail(node) {
  selectedNode.value = node
  showDetailDialog.value = true
}

// 在图谱中查看
function viewInGraph(node) {
  router.push({
    path: '/graph',
    query: { focus: node.node_id || node.name }
  })
}

// 获取节点操作按钮文本
function getNodeActionButtonText(label) {
  const textMap = {
    'Question': '查看题目',
    'KnowledgeNode': '查看知识点',
    '知识点': '查看知识点'
  }
  return textMap[label] || '在图谱中查看'
}

// 根据节点类型执行不同操作
function handleNodeAction(node) {
  const label = node.label
  
  // 题目 -> 跳转到题目页面
  if (label === 'Question') {
    router.push({
      path: '/questions',
      query: { id: node.node_id || node.id }
    })
    showDetailDialog.value = false
    return
  }
  
  // 知识点 -> 跳转到知识点页面
  if (label === 'KnowledgeNode' || label === '知识点') {
    router.push({
      path: '/knowledge',
      query: { focus: node.node_id || node.name }
    })
    showDetailDialog.value = false
    return
  }
  
  // 其他节点 -> 在图谱中查看
  viewInGraph(node)
  showDetailDialog.value = false
}

// 获取节点类型标签颜色
function getNodeTypeTagColor(type) {
  return getNodeTypeTagType(type)
}

// 截断文本
function truncateText(text, maxLength) {
  if (!text) return ''
  return text.length > maxLength ? text.substring(0, maxLength) + '...' : text
}

function highlightSegments(text, keyword = lastSearchKeyword.value) {
  const source = String(text || '')
  const target = String(keyword || '').trim()
  if (!source || !target) return [{ text: source, matched: false }]

  const sourceLower = source.toLocaleLowerCase('zh-CN')
  const targetLower = target.toLocaleLowerCase('zh-CN')
  const segments = []
  let cursor = 0
  let matchIndex = sourceLower.indexOf(targetLower)
  while (matchIndex !== -1) {
    if (matchIndex > cursor) {
      segments.push({ text: source.slice(cursor, matchIndex), matched: false })
    }
    segments.push({
      text: source.slice(matchIndex, matchIndex + target.length),
      matched: true
    })
    cursor = matchIndex + target.length
    matchIndex = sourceLower.indexOf(targetLower, cursor)
  }
  if (cursor < source.length) segments.push({ text: source.slice(cursor), matched: false })
  return segments.length ? segments : [{ text: source, matched: false }]
}

function formatSearchScore(score) {
  const value = Number(score)
  return Number.isFinite(value) ? value.toFixed(2) : '0.00'
}

// 格式化值
function formatValue(value) {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function handleDocumentClick(e) {
  if (!e.target.closest('.suggestions') && !e.target.closest('.search-input-col')) {
    showSuggestions.value = false
  }
}

// 点击外部关闭下拉框
onMounted(() => document.addEventListener('click', handleDocumentClick))
</script>

<style scoped>
.search-page {
  padding: 20px;
}

.search-card {
  position: relative;
}

.search-input-col {
  position: relative;
}

.search-submit {
  width: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.results-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 16px;
  padding: 10px;
}

.result-card {
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  transition: all 0.3s;
}

.result-card:hover {
  border-color: #409eff;
  box-shadow: 0 2px 12px rgba(64, 158, 255, 0.15);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.result-id {
  font-size: 12px;
  color: #909399;
  font-family: monospace;
}

.result-name {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  cursor: pointer;
  margin-bottom: 8px;
}

.result-name:hover {
  color: #409eff;
}

.result-overview {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
  margin-bottom: 8px;
}

.result-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.result-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.result-actions {
  display: flex;
  justify-content: flex-end;
}

:deep(.el-dialog) {
  max-width: calc(100vw - 24px);
}

@media (max-width: 900px) {
  .search-page {
    padding: 0;
  }

  .search-controls {
    row-gap: 10px;
  }

  .search-controls > :deep(.el-col) {
    flex: 0 0 100%;
    max-width: 100%;
  }

  .results-container {
    grid-template-columns: minmax(0, 1fr);
    padding: 0;
  }

  .card-header,
  .result-header {
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 8px;
  }

  .result-card {
    padding: 12px;
  }

  .result-name,
  .result-overview {
    overflow-wrap: anywhere;
  }
}
</style>

<style>
/* 全局样式 - 应用于teleport到body的元素 */
.suggestions {
  position: fixed;
  background: white;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  max-height: 320px;
  overflow-y: auto;
  z-index: 9999;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  max-width: calc(100vw - 24px);
}

.suggestions::-webkit-scrollbar {
  width: 6px;
}

.suggestions::-webkit-scrollbar-thumb {
  background-color: #dcdfe6;
  border-radius: 3px;
}

.suggestions::-webkit-scrollbar-track {
  background-color: #f5f7fa;
}

.suggestion-item {
  padding: 12px 16px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #f0f0f0;
  transition: background 0.2s;
}

.suggestion-item:last-child {
  border-bottom: none;
}

.suggestion-item:hover {
  background-color: #f5f7fa;
}

.suggestion-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  overflow: hidden;
}

.suggestion-name {
  font-size: 14px;
  color: #303133;
  font-weight: 500;
}

.search-highlight {
  color: #c2410c;
  background: #ffedd5;
  border-radius: 3px;
  padding: 0 2px;
}

.score-tag {
  margin-left: auto;
}

.suggestion-sub {
  font-size: 12px;
  color: #606266;
}

.suggestion-section {
  font-size: 12px;
  color: #909399;
}
</style>
