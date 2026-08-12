<template>
  <div class="graph-page">
    <div class="graph-header">
      <span class="title">📊 知识图谱可视化</span>
      <div class="header-actions">
        <el-input
          v-model="searchNodeKeyword"
          class="graph-search-input"
          placeholder="搜索节点..."
          size="small"
          @input="handleSearchInput"
          @focus="handleSearchFocus"
          @keyup.enter="searchAndFocusNode"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <div v-if="showSearchHistory && searchHistory.length" class="search-results-dropdown search-history-dropdown">
          <div class="search-history-header">
            <span>最近搜索</span>
            <el-button link size="small" @click.stop="clearSearchHistory">清空</el-button>
          </div>
          <div
            v-for="keyword in searchHistory"
            :key="keyword"
            class="search-result-item history-item"
            @click="selectSearchHistory(keyword)"
          >
            <el-icon class="history-icon"><Clock /></el-icon>
            <span class="result-name">{{ keyword }}</span>
            <el-button
              link
              circle
              :icon="Close"
              title="删除这条搜索记录"
              @click.stop="removeSearchHistory(keyword)"
            />
          </div>
        </div>
        <!-- 搜索结果下拉 -->
        <div v-if="searchResults.length > 0 && showSearchResults" class="search-results-dropdown">
          <div 
            v-for="item in searchResults" 
            :key="item.id" 
            class="search-result-item"
            @click="focusSearchResult(item)"
          >
            <span class="result-name">{{ item.name }}</span>
            <el-tag size="small" :type="item.type === 'Chapter' ? 'success' : 'primary'">
              {{ nodeTypeLabels[item.type] || item.type }}
            </el-tag>
          </div>
        </div>
        <el-switch
          v-model="masteryViewEnabled"
          class="mastery-toggle"
          active-text="掌握度视图"
          @change="handleMasteryViewChange"
        />
        <el-tag size="small" effect="plain">状态 v{{ learningRevision }}</el-tag>
        <el-switch
          v-model="mistakeViewEnabled"
          class="mistake-toggle"
          active-text="错题视图"
          @change="handleMistakeViewChange"
        />
        <el-button :icon="Refresh" :loading="graphLoading" @click="restoreDefaultView">
          恢复默认
        </el-button>
        <el-button @click="toggleChapterClusters">
          {{ clustersActive ? '展开聚类' : '按章节聚类' }}
        </el-button>
        <el-button v-if="pathHighlightCount" type="warning" plain @click="clearPathHighlight">
          清除路径高亮 ({{ pathHighlightCount }})
        </el-button>
        <el-button @click="showNodeFilter = true">筛选</el-button>
        <el-button @click="showStats = true">统计</el-button>
        <el-button type="primary" @click="fitToScreen">适应屏幕</el-button>
        <el-button :icon="Download" :disabled="graphLoading" @click="exportGraphAsPng">
          导出 PNG
        </el-button>
      </div>
    </div>

    <!-- 图谱容器 -->
    <div class="graph-container-wrapper">
      <div id="graph-container" ref="graphContainer"></div>
      
      <!-- 图例 -->
      <div class="legend-panel" :class="{ 'is-collapsed': !showLegend }">
        <div class="legend-header">
          <span>图例</span>
          <el-tooltip :content="showLegend ? '收起图例' : '展开图例'" placement="left">
            <el-button
              link
              circle
              :icon="showLegend ? ArrowUp : ArrowDown"
              :aria-label="showLegend ? '收起图例' : '展开图例'"
              @click="showLegend = !showLegend"
            />
          </el-tooltip>
        </div>
        <div v-show="showLegend" class="legend-content">
          <template v-if="mistakeViewEnabled">
            <div class="legend-title">错题标记</div>
            <div class="legend-items">
              <div class="legend-item">
                <span class="legend-color legend-mistake-marker"></span>
                <span class="legend-label">有错题关联</span>
                <span class="legend-count">{{ mistakeNodeCount }}</span>
              </div>
            </div>
            <div class="legend-note">🔮 紫色虚线边框：有错题关联的知识点（数字为错题数量）</div>
            <div class="legend-divider"></div>
          </template>
          <template v-if="masteryViewEnabled">
            <div class="legend-title">知识点掌握状态</div>
            <div class="legend-items">
              <div v-for="item in masteryLegendItems" :key="item.key" class="legend-item">
                <span class="legend-color" :style="getMasteryLegendStyle(item.key)"></span>
                <span class="legend-label">{{ item.label }}</span>
                <span class="legend-count">{{ visibleMasteryStatusCounts[item.key] || 0 }}</span>
              </div>
            </div>
            <div class="legend-divider"></div>
          </template>
          <div class="legend-title">{{ masteryViewEnabled ? '其他实体类型' : '实体类型' }}</div>
          <div class="legend-items">
            <div v-for="type in legendNodeTypes" :key="type" class="legend-item">
              <span class="legend-color" :style="getNodeLegendStyle(type)"></span>
              <span class="legend-label">{{ nodeTypeLabels[type] || type }}</span>
              <span class="legend-count">{{ visibleNodeTypeCounts[type] || 0 }}</span>
            </div>
          </div>
          <template v-if="!masteryViewEnabled">
            <div class="legend-divider"></div>
            <div class="legend-title">题目难度等级</div>
            <div class="legend-items">
              <div v-for="item in difficultyLegendItems" :key="item.level" class="legend-item">
                <span class="legend-color" :style="getDifficultyLegendStyle(item.level)"></span>
                <span class="legend-label">{{ item.level }}</span>
                <span class="legend-count">{{ item.count }}</span>
              </div>
            </div>
          </template>
          <template v-if="!masteryViewEnabled">
            <div class="legend-divider"></div>
            <div class="legend-title">知识节点类型</div>
            <div class="legend-items">
              <div v-for="type in knowledgeSubtypeTypes" :key="type" class="legend-item">
                <span class="legend-color" :style="getNodeLegendStyle(type)"></span>
                <span class="legend-label">{{ nodeTypeLabels[type] || type }}</span>
                <span class="legend-count">{{ visibleKnowledgeSubtypeCounts[type] || 0 }}</span>
              </div>
            </div>
          </template>
          <div class="legend-divider"></div>
          <div class="legend-title">关系类型</div>
          <div class="legend-items">
            <div v-for="type in relationTypes" :key="type" class="legend-item">
              <span class="legend-line" :style="{ background: getRelationColor(type) }"></span>
              <span class="legend-label">{{ relationTypeLabels[type] || type }}</span>
              <span class="legend-count">{{ visibleRelationTypeCounts[type] || 0 }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 节点筛选对话框 -->
    <el-dialog v-model="showNodeFilter" title="节点筛选" width="500px">
      <el-form label-width="100px">
        <el-form-item label="节点类型">
          <el-checkbox-group v-model="selectedNodeTypes">
            <el-checkbox v-for="label in nodeTypes" :key="label" :label="label">
              {{ nodeTypeLabels[label] || label }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="关系类型">
          <el-checkbox-group v-model="selectedRelTypes">
            <el-checkbox v-for="rel in relationTypes" :key="rel" :label="rel">
              {{ relationTypeLabels[rel] || rel }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="节点数量">
          <el-slider v-model="nodeLimit" :min="50" :max="2000" show-input />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showNodeFilter = false">取消</el-button>
        <el-button type="primary" @click="applyFilter">应用</el-button>
      </template>
    </el-dialog>

    <!-- 统计信息对话框 -->
    <el-dialog v-model="showStats" title="图谱统计" width="700px">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="总节点数">
          {{ statistics.total_nodes }}
        </el-descriptions-item>
        <el-descriptions-item label="总关系数">
          {{ statistics.total_relationships }}
        </el-descriptions-item>
      </el-descriptions>
      
      <h4 style="margin: 20px 0 10px">节点类型分布</h4>
      <el-table :data="nodeTypeStats" size="small" max-height="200">
        <el-table-column prop="label" label="类型" />
        <el-table-column prop="count" label="数量" />
        <el-table-column label="占比">
          <template #default="{ row }">
            {{ (row.count / statistics.total_nodes * 100).toFixed(1) }}%
          </template>
        </el-table-column>
      </el-table>
      
      <h4 style="margin: 20px 0 10px">关系类型分布</h4>
      <el-table :data="relationTypeStats" size="small" max-height="200">
        <el-table-column prop="label" label="类型">
          <template #default="{ row }">
            <el-tag size="small" :color="getRelationColor(row.type)" effect="dark">
              {{ row.label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="count" label="数量" />
        <el-table-column label="占比">
          <template #default="{ row }">
            {{ (row.count / statistics.total_relationships * 100).toFixed(1) }}%
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 节点详情抽屉 -->
    <el-drawer v-model="showNodeDetail" :title="nodeDetailTitle" size="450px">
      <div v-if="selectedNode" class="node-detail-content">
        <!-- 基本信息 -->
        <div class="detail-section">
          <h4>基本信息</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="名称">{{ selectedNode.name }}</el-descriptions-item>
            <el-descriptions-item label="类型">
              <el-tag size="small" :type="getTypeTagColor(getNodeTypeKey(selectedNode))">
                {{ getNodeTypeLabel(selectedNode) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item v-if="selectedNode.section" label="章节">
              {{ selectedNode.section }}
            </el-descriptions-item>
            <el-descriptions-item v-if="selectedNode.level" label="难度">
              {{ selectedNode.level }}
            </el-descriptions-item>
          </el-descriptions>
        </div>
        
        <!-- 概述 -->
        <div v-if="selectedNode.overview" class="detail-section">
          <h4>核心概述</h4>
          <p class="overview-text">{{ selectedNode.overview }}</p>
        </div>
        
        <!-- 标签 -->
        <div v-if="displayTags.length" class="detail-section">
          <h4>标签</h4>
          <div class="tags-wrapper">
            <el-tag
              v-for="tag in displayTags"
              :key="tag"
              class="node-tag"
              size="small"
              type="info"
              effect="plain"
              :title="tag"
            >
              {{ tag }}
            </el-tag>
          </div>
        </div>
        
        <!-- 相关节点 -->
        <div v-if="nodeRelationships.length > 0" class="detail-section">
          <h4>相关节点 ({{ nodeRelationships.length }})</h4>
          <el-table :data="nodeRelationships" size="small" max-height="300">
            <el-table-column prop="relationship.type" label="关系" width="120">
              <template #default="{ row }">
                <el-tag size="small" :color="getRelationColor(row.relationship.type)" effect="dark">
                  {{ relationTypeLabels[row.relationship.type] || row.relationship.type }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="target.name" label="目标节点">
              <template #default="{ row }">
                <el-link type="primary" @click="openRelatedNode(row)">
                  {{ row.target.name }}
                </el-link>
              </template>
            </el-table-column>
          </el-table>
        </div>
        
        <!-- 操作按钮 -->
        <div class="detail-actions">
          <el-button @click="toggleNodeExpansion(selectedNode.id)">
            {{ expandedNodeIds.has(selectedNode.id) ? '折叠邻居' : '展开邻居' }}
          </el-button>
          <el-button type="primary" @click="viewNodeDetail">
            {{ getNodeDetailButtonText() }}
          </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getGraphData,
  getGraphFragment,
  getStatistics,
  getLabels,
  getNodeDetail,
  getNodeNeighbors,
  getRelationshipTypes
} from '@/api/graph'
import { ElMessage } from 'element-plus'
import { ArrowDown, ArrowUp, Clock, Close, Download, Refresh, Search } from '@element-plus/icons-vue'
import { DataSet, Network } from 'vis-network/standalone'
import { searchNodes } from '@/api/search'
import { useGraphElements } from '@/composables/useGraphElements'
import { normalizeNodeTags } from '@/utils/nodeTags'
import { normalizeSearchTerm, resolveCanonicalGraphTarget } from '@/utils/searchTerms'
import { getLearningState, getMistakes, loadLearningState } from '@/stores/progress'
import { MASTERY_STATE_META, getMasteryState } from '@/utils/learningDashboard'
import {
  DIFFICULTY_LEVEL_COLORS,
  DIFFICULTY_LEVEL_ORDER,
  KNOWLEDGE_SUBTYPE_TYPES,
  NODE_TYPE_COLORS,
  NODE_TYPE_LABELS,
  PREFERRED_NODE_TYPE_ORDER,
  getNodeTypeTagType
} from '@/utils/nodeTypes'
import { collectRetainedGraphIds } from '@/utils/graphFragments'

const route = useRoute()
const router = useRouter()
const masteryViewEnabled = ref(String(route.query.mastery || '') === '1')
const mistakeViewEnabled = ref(false)
let learningState = getLearningState()
const learningRevision = ref(learningState.revision)

const graphContainer = ref(null)
let network = null
let nodesDataSet = null
let edgesDataSet = null
let networkStabilized = false
const baseNodeIds = new Set()
const baseEdgeIds = new Set()
const retainedFragmentNodeIds = new Set()
const retainedFragmentEdgeIds = new Set()
const expansionFragments = new Map()
const expandedNodeIds = reactive(new Set())
const expandingNodeIds = new Set()
const activeClusterIds = new Set()
const clustersActive = ref(false)
const highlightedPathNodeIds = ref([])
const highlightedPathEdgeIds = ref([])
const pathHighlightCount = computed(() => highlightedPathNodeIds.value.length)

function destroyNetwork() {
  if (network) {
    network.destroy()
    network = null
    networkStabilized = false
  }
  activeClusterIds.clear()
  clustersActive.value = false
}

const showNodeFilter = ref(false)
const showStats = ref(false)
const showNodeDetail = ref(false)
const showLegend = ref(true)
const graphLoading = ref(false)
const searchNodeKeyword = ref('')
const searchResults = ref([])
const showSearchResults = ref(false)

let searchTimer = null
const SEARCH_HISTORY_KEY = 'knowledge-graph-search-history'
const SEARCH_HISTORY_LIMIT = 10
const searchHistory = ref(loadSearchHistory())
const showSearchHistory = ref(false)

const nodeTypes = ref(['KnowledgeNode', 'Chapter', 'Question'])
const selectedNodeTypes = ref(['KnowledgeNode', 'Chapter', 'Question'])
const relationTypes = ref([])
const selectedRelTypes = ref([])
const nodeLimit = ref(200)

const statistics = ref({
  total_nodes: 0,
  total_relationships: 0,
  nodes: {},
  relationships: {}
})

const selectedNode = ref({})
const nodeRelationships = ref([])
const displayTags = computed(() => normalizeNodeTags(selectedNode.value))
const visibleNodeTypeCounts = ref({})
const visibleDifficultyCounts = ref({})
const visibleKnowledgeSubtypeCounts = ref({})
const visibleRelationTypeCounts = ref({})
const visibleMasteryStatusCounts = ref({})

const graphGroups = Object.fromEntries(
  Object.entries(NODE_TYPE_COLORS).map(([type, color]) => [type, {
    color: {
      background: color,
      border: type === 'KnowledgeNode' ? '#2563eb' : color,
      highlight: { background: color, border: '#111827' },
      hover: { background: color, border: '#1d4ed8' }
    }
  }])
)

const preferredNodeTypeOrder = PREFERRED_NODE_TYPE_ORDER
const knowledgeSubtypeTypes = KNOWLEDGE_SUBTYPE_TYPES
const nodeTypeLabels = NODE_TYPE_LABELS
const difficultyLevelOrder = DIFFICULTY_LEVEL_ORDER
const difficultyLevelColors = DIFFICULTY_LEVEL_COLORS
const difficultyLegendItems = computed(() => difficultyLevelOrder.map(level => ({
  level,
  count: visibleDifficultyCounts.value[level] || 0
})))

// 关系颜色映射
const relationColors = {
  'BELONGS_TO': '#67c23a',
  'PREREQUISITE': '#f56c6c',
  'HAS_CORE_RELATION': '#409eff',
  'APPLIED_IN': '#e6a23c',
  'HAS_INSTANCE': '#909399',
  'HAS_CORE_CONCEPT': '#9c27b0',
  'IS_ABSTRACT_CONCEPT': '#5470c6',
  'IS_CONCRETE_ENTITY': '#91cc75',
  'IS_KEY_EVENT': '#fac858',
  'RELATED_TO': '#c0c4cc',
  'REQUIRES': '#0ea5e9',
  'HAS_DIFFICULTY': '#d97706',
  'USED_BY': '#64748b'
}

// 关系类型中文映射
const relationTypeLabels = {
  'BELONGS_TO': '隶属',
  'PREREQUISITE': '前置知识',
  'HAS_CORE_RELATION': '核心关联',
  'APPLIED_IN': '应用场景',
  'HAS_INSTANCE': '包含实例',
  'HAS_CORE_CONCEPT': '核心概念',
  'IS_ABSTRACT_CONCEPT': '抽象概念',
  'IS_CONCRETE_ENTITY': '具体实体',
  'IS_KEY_EVENT': '关键事件',
  'RELATED_TO': '相关',
  'REQUIRES': '考查知识',
  'HAS_DIFFICULTY': '题目难度',
  'USED_BY': '被使用'
}

const { toGraphNode, toGraphEdge } = useGraphElements({
  getNodeColor,
  getRelationColor,
  relationTypeLabels,
  generateTooltip
})

// 包装toGraphNode以添加错题角标
function toGraphNodeWithMistake(node) {
  const graphNode = toGraphNode(node)
  if (mistakeViewEnabled.value && node.type === 'KnowledgeNode') {
    const mistakeCount = mistakeCountMap.value.get(node.id || node.node_id) || 0
    if (mistakeCount > 0) {
      graphNode.label = `${node.label} (${mistakeCount}错)`
      graphNode.font = { ...graphNode.font, size: 15, bold: true }
      graphNode.size = (graphNode.size || 18) + 3  // 稍微放大
      graphNode.borderWidth = 3  // 3px边框
      graphNode.borderWidthSelected = 5
      graphNode.shapeProperties = {
        borderDashes: [5, 5]  // 虚线效果：5px实线 + 5px空隙
      }
    }
  }
  return graphNode
}

const displayedNodeTypes = computed(() => {
  const available = new Set(nodeTypes.value)
  return [
    ...preferredNodeTypeOrder.filter(type => available.has(type)),
    ...nodeTypes.value.filter(type => !preferredNodeTypeOrder.includes(type))
  ]
})
const legendNodeTypes = computed(() => masteryViewEnabled.value
  ? displayedNodeTypes.value.filter(type => type !== 'KnowledgeNode')
  : displayedNodeTypes.value
)
const masteryLegendItems = Object.entries(MASTERY_STATE_META).map(([key, value]) => ({ key, ...value }))

// 错题计数映射
const mistakeCountMap = computed(() => {
  void learningRevision.value
  if (!mistakeViewEnabled.value) return new Map()
  const map = new Map()
  const mistakes = getMistakes()
  mistakes.forEach(record => {
    (record.knowledge_ids || []).forEach(id => {
      const currentCount = map.get(id) || 0
      map.set(id, currentCount + 1)
    })
  })
  return map
})

// 错题相关节点集合（知识点 + 题目节点）
const mistakeRelatedNodeIds = computed(() => {
  if (!mistakeViewEnabled.value) return new Set()
  const relatedIds = new Set()
  const mistakes = getMistakes()

  // 1. 添加所有有错题的知识点
  mistakeCountMap.value.forEach((count, nodeId) => {
    relatedIds.add(nodeId)
  })

  // 2. 添加所有错题题目节点
  mistakes.forEach(record => {
    relatedIds.add(record.question_id)
  })

  return relatedIds
})

// 有错题的节点总数
const mistakeNodeCount = computed(() => {
  return mistakeCountMap.value.size
})

// 计算节点类型统计
const nodeTypeStats = computed(() => {
  return Object.entries(statistics.value.nodes || {}).map(([type, count]) => ({
    type,
    label: nodeTypeLabels[type] || type,
    count
  }))
})

// 计算关系类型统计
const relationTypeStats = computed(() => {
  return Object.entries(statistics.value.relationships || {}).map(([type, count]) => ({
    type,
    label: relationTypeLabels[type] || type,
    count
  }))
})

// 节点详情标题
const nodeDetailTitle = computed(() => {
  return selectedNode.value.name || '节点详情'
})

// 初始化图谱
async function initGraph() {
  try {
    // 获取节点标签
    const labelsRes = await getLabels()
    if (labelsRes.success) {
      nodeTypes.value = labelsRes.data
      selectedNodeTypes.value = [...labelsRes.data]
    }

    // 获取关系类型
    const relTypesRes = await getRelationshipTypes()
    if (relTypesRes.success) {
      relationTypes.value = relTypesRes.data
      selectedRelTypes.value = [...relTypesRes.data]
    }

    // 加载图谱数据
    await loadGraphData()

    // 获取统计信息
    const statsRes = await getStatistics()
    if (statsRes.success) {
      statistics.value = statsRes.data
    }
  } catch (error) {
    ElMessage.error('加载图谱失败')
    console.error(error)
  }
}

// 加载图谱数据
async function loadGraphData() {
  graphLoading.value = true
  try {
    learningState = getLearningState()
    const res = await getGraphData(nodeLimit.value, selectedNodeTypes.value)
    if (res.success && res.data) {
      const { nodes, edges } = res.data
      const visibleEdges = relationTypes.value.length === 0
        ? edges
        : edges.filter(edge => selectedRelTypes.value.includes(edge.label))

      visibleNodeTypeCounts.value = countBy(nodes, node => node.type)
      visibleDifficultyCounts.value = countBy(
        nodes.filter(node => node.type === 'Difficulty'),
        node => node.properties?.level
      )
      visibleKnowledgeSubtypeCounts.value = countBy(
        nodes.filter(node => node.type === 'KnowledgeNode'),
        node => node.properties?.node_type
      )
      visibleRelationTypeCounts.value = countBy(visibleEdges, edge => edge.label)
      visibleMasteryStatusCounts.value = countBy(
        nodes.filter(node => node.type === 'KnowledgeNode'),
        getNodeLearningStatus
      )

      // 创建数据集
      nodesDataSet = new DataSet(nodes.map(toGraphNodeWithMistake))
      edgesDataSet = new DataSet(visibleEdges.map(toGraphEdge))
      baseNodeIds.clear()
      baseEdgeIds.clear()
      retainedFragmentNodeIds.clear()
      retainedFragmentEdgeIds.clear()
      expansionFragments.clear()
      nodes.forEach(node => baseNodeIds.add(node.id))
      visibleEdges.forEach(edge => baseEdgeIds.add(toGraphEdge(edge).id))
      expandedNodeIds.clear()
      highlightedPathNodeIds.value = []
      highlightedPathEdgeIds.value = []

      // 创建图谱实例
      const data = { nodes: nodesDataSet, edges: edgesDataSet }
      const options = {
        groups: graphGroups,
        nodes: {
          shape: 'dot',
          font: { 
            size: 14,
            face: 'Microsoft YaHei, Arial, sans-serif'
          },
          borderWidth: 2,
          borderWidthSelected: 5,
          shadow: true
        },
        edges: {
          width: 1.5,
          smooth: { type: 'continuous', roundness: 0.5 },
          font: {
            size: 11,
            align: 'middle',
            background: 'white'
          }
        },
        physics: {
          enabled: true,
          barnesHut: {
            gravitationalConstant: -12000,
            centralGravity: 0.05,
            springLength: 500,
            springConstant: 0.02,
            damping: 1,
            avoidOverlap: 0.5
          },
          stabilization: {
            enabled: true,
            iterations: 500,
            updateInterval: 100,
            fit: true
          }
        },
        layout: {
          improvedLayout: true,
          clusterThreshold: 150
        },
        interaction: {
          hover: true,
          tooltipDelay: 150,
          zoomView: true,
          dragView: true,
          dragNodes: true,
          navigationButtons: true,
          keyboard: {
            enabled: true,
            bindToWindow: false,
            speed: { x: 10, y: 10, zoom: 0.02 }
          }
        }
      }

      destroyNetwork()
      network = new Network(graphContainer.value, data, options)

      // 事件监听
      network.on('click', handleNodeClick)
      network.on('doubleClick', handleNodeDoubleClick)
      network.on('hoverNode', handleNodeHover)
      
      let loadNotified = false
      network.on('stabilizationIterationsDone', () => {
        networkStabilized = true
        if (!loadNotified) {
          loadNotified = true
          ElMessage.success('图谱加载完成')
        }
      })
    }
  } catch (error) {
    ElMessage.error('加载图谱数据失败')
    console.error(error)
  } finally {
    graphLoading.value = false
  }
}

// 生成节点提示（纯文本 + \n 换行，兼容 vis-network）
function generateTooltip(node) {
  const props = node.properties || {}
  const lines = [node.label]
  const typeKey = props.node_type || node.type
  const typeLabel = nodeTypeLabels[typeKey] || typeKey
  if (typeLabel) lines.push('类型：' + typeLabel)
  if (node.type === 'Difficulty' && props.level) lines.push('难度：' + props.level)
  if (props.section) lines.push('章节：' + props.section)
  if (props.overview) lines.push(props.overview.substring(0, 100) + '...')
  return lines.join('\n')
}

// 获取节点颜色
function getNodeColor(node) {
  const nodeId = node.id || node.node_id

  // 错题视图：紫色虚线边框标记有错题的知识点，淡化无关节点
  if (mistakeViewEnabled.value && node.type === 'KnowledgeNode') {
    const mistakeCount = mistakeCountMap.value.get(nodeId) || 0
    const isRelated = mistakeRelatedNodeIds.value.has(nodeId)

    if (mistakeCount > 0) {
      // 有错题的知识点：紫色虚线边框
      let background = '#409eff'
      if (masteryViewEnabled.value) {
        const status = getNodeLearningStatus(node)
        background = MASTERY_STATE_META[status].color
      } else if (node.properties?.node_type) {
        background = NODE_TYPE_COLORS[node.properties.node_type] || NODE_TYPE_COLORS.KnowledgeNode
      }

      return {
        background,
        border: '#9333ea', // 紫色边框
        highlight: { background, border: '#7e22ce' },
        hover: { background, border: '#7e22ce' }
      }
    } else if (!isRelated) {
      // 无关节点：淡化为半透明灰色
      return {
        background: '#e5e7eb',
        border: '#d1d5db',
        highlight: { background: '#e5e7eb', border: '#9ca3af' },
        hover: { background: '#e5e7eb', border: '#9ca3af' }
      }
    }
  }

  // 错题视图下的题目节点：有错题的保持红色，无错题的淡化
  if (mistakeViewEnabled.value && node.type === 'Question') {
    const isRelated = mistakeRelatedNodeIds.value.has(nodeId)
    if (!isRelated) {
      // 不是错题的题目节点：淡化
      return {
        background: '#fca5a5',
        border: '#f87171',
        highlight: { background: '#fca5a5', border: '#ef4444' },
        hover: { background: '#fca5a5', border: '#ef4444' }
      }
    }
  }

  // 错题视图下的其他节点（章节、难度等）：淡化
  if (mistakeViewEnabled.value && !mistakeRelatedNodeIds.value.has(nodeId)) {
    return {
      background: '#e5e7eb',
      border: '#d1d5db',
      highlight: { background: '#e5e7eb', border: '#9ca3af' },
      hover: { background: '#e5e7eb', border: '#9ca3af' }
    }
  }

  if (masteryViewEnabled.value && node.type === 'KnowledgeNode') {
    const status = getNodeLearningStatus(node)
    const meta = MASTERY_STATE_META[status]
    const color = meta.color
    const border = meta.border
    return {
      background: color,
      border,
      highlight: { background: color, border: '#1d4ed8' },
      hover: { background: color, border: '#1d4ed8' }
    }
  }
  if (node.type === 'KnowledgeNode' && node.properties?.node_type) {
    const background = NODE_TYPE_COLORS[node.properties.node_type] || NODE_TYPE_COLORS.KnowledgeNode
    return {
      background,
      border: NODE_TYPE_COLORS.KnowledgeNode,
      highlight: { background, border: '#1d4ed8' },
      hover: { background, border: '#1d4ed8' }
    }
  }
  if (node.type === 'Difficulty' && node.properties?.level) {
    const background = difficultyLevelColors[node.properties.level] || NODE_TYPE_COLORS.Difficulty
    return {
      background,
      border: background,
      highlight: { background, border: '#111827' },
      hover: { background, border: '#111827' }
    }
  }
  return NODE_TYPE_COLORS[node.type] || '#409eff'
}

function getNodeLearningStatus(node) {
  const id = String(node?.id || node?.node_id || node?.properties?.id || node?.properties?.node_id || '')
  return getMasteryState(learningState.progress?.[id], learningState.mastered?.[id])
}

function getNodeLegendStyle(type) {
  const color = NODE_TYPE_COLORS[type] || '#409eff'
  if (type === 'KnowledgeNode') {
    return { background: '#fff', border: `3px solid ${color}` }
  }
  return { background: color, border: `2px solid ${color}` }
}

function getDifficultyLegendStyle(level) {
  const color = difficultyLevelColors[level] || NODE_TYPE_COLORS.Difficulty
  return { background: color, border: `2px solid ${color}` }
}

function getMasteryLegendStyle(status) {
  const color = MASTERY_STATE_META[status]?.color || '#c0c4cc'
  return { background: color, border: `2px solid ${color}` }
}

function getRelationColor(type) {
  return relationColors[type] || '#64748b'
}

function countBy(items, getKey) {
  return items.reduce((counts, item) => {
    const key = getKey(item)
    if (key) counts[key] = (counts[key] || 0) + 1
    return counts
  }, {})
}

// 获取类型标签颜色
function getTypeTagColor(type) {
  return getNodeTypeTagType(type)
}

function getNodeTypeKey(node) {
  return node?.node_type || node?.label || node?.type || ''
}

function getNodeTypeLabel(node) {
  const type = getNodeTypeKey(node)
  return nodeTypeLabels[type] || type || '未知类型'
}

// 节点点击事件
async function handleNodeClick(params) {
  if (params.nodes.length > 0) {
    const nodeId = params.nodes[0]
    const node = nodesDataSet.get(nodeId)
    
    selectedNode.value = {
      ...node.properties,
      id: nodeId,
      name: node.label,
      label: node.nodeType || node.group  // 节点业务类型
    }

    // 获取节点详情
    try {
      const res = await getNodeDetail(nodeId, 'both')
      if (res.success && res.data) {
        // 去重：同一目标节点可能以不同关系类型出现多次，按 target.id + relationship.type 去重
        const seen = new Set()
        nodeRelationships.value = res.data.relationships
          .map(rel => ({ relationship: rel.relationship, target: rel.target }))
          .filter(item => {
            const key = `${item.target?.id}::${item.relationship?.type}`
            if (seen.has(key)) return false
            seen.add(key)
            return true
          })
      }
    } catch (error) {
      console.error('获取节点详情失败:', error)
    }

    showNodeDetail.value = true
  }
}

async function expandNode(nodeId, { focus = true } = {}) {
  if (!nodeId || expandingNodeIds.has(nodeId)) return
  if (expandedNodeIds.has(nodeId)) {
    if (focus) await focusOnNodeWhenStable(nodeId)
    ElMessage.info('该节点的邻居已展开')
    return
  }

  expandingNodeIds.add(nodeId)
  try {
    const res = await getNodeNeighbors(nodeId, 30, selectedRelTypes.value)
    if (!res.success || !res.data) return
    const { newNodes, newEdges } = mergeGraphFragment(res.data, { expansionRoot: nodeId })
    expandedNodeIds.add(nodeId)
    if (!networkStabilized) await stabilizeNetwork()
    if (focus) {
      focusOnNodeById(nodeId, 1.2)
    }
    if (newNodes.length || newEdges.length) {
      ElMessage.success(`新增 ${newNodes.length} 个节点、${newEdges.length} 条关系`)
    } else {
      ElMessage.info(`邻居节点均已在图谱中（共 ${res.data.nodes?.length ?? 0} 个）`)
    }
  } catch (error) {
    console.error('展开邻居失败:', error)
    ElMessage.error('展开邻居失败')
  } finally {
    expandingNodeIds.delete(nodeId)
  }
}

async function toggleNodeExpansion(nodeId) {
  if (expandedNodeIds.has(nodeId)) await collapseNode(nodeId)
  else await expandNode(nodeId)
}

async function collapseNode(nodeId) {
  if (!expandedNodeIds.has(nodeId) || !nodesDataSet || !edgesDataSet) return

  expansionFragments.delete(nodeId)
  expandedNodeIds.delete(nodeId)
  const { nodeIds, edgeIds } = collectRetainedGraphIds({
    baseNodeIds,
    baseEdgeIds,
    retainedNodeIds: retainedFragmentNodeIds,
    retainedEdgeIds: retainedFragmentEdgeIds,
    expansionFragments
  })
  const removedEdgeIds = edgesDataSet.getIds().filter(id => !edgeIds.has(id))
  const removedNodeIds = nodesDataSet.getIds().filter(id => !nodeIds.has(id))
  if (removedEdgeIds.length) edgesDataSet.remove(removedEdgeIds)
  if (removedNodeIds.length) nodesDataSet.remove(removedNodeIds)
  refreshVisibleCounts()
  // 只有真正删了节点/边时才重新稳定布局，避免无事发生时触发 fit 缩放
  if (removedNodeIds.length || removedEdgeIds.length) {
    networkStabilized = false
    await stabilizeNetwork()
  }
  if (removedNodeIds.length || removedEdgeIds.length) {
    ElMessage.success(`已折叠 ${removedNodeIds.length} 个节点、${removedEdgeIds.length} 条关系`)
  } else {
    ElMessage.info('邻居节点均来自基础图谱，无需折叠')
  }
}

function mergeGraphFragment(fragment, { expansionRoot = null, retain = false } = {}) {
  const fragmentNodeIds = new Set((fragment.nodes || []).map(node => node.id))
  const fragmentEdgeIds = new Set((fragment.edges || []).map(edge => toGraphEdge(edge).id))
  if (expansionRoot) fragmentNodeIds.add(expansionRoot)

  const newNodes = (fragment.nodes || []).filter(node => !nodesDataSet.get(node.id))
  const newEdges = (fragment.edges || []).filter(edge => !edgesDataSet.get(toGraphEdge(edge).id))
  if (newNodes.length) nodesDataSet.add(newNodes.map(toGraphNodeWithMistake))
  if (newEdges.length) edgesDataSet.add(newEdges.map(toGraphEdge))
  if (expansionRoot) expansionFragments.set(expansionRoot, { nodeIds: fragmentNodeIds, edgeIds: fragmentEdgeIds })
  if (retain) {
    fragmentNodeIds.forEach(id => retainedFragmentNodeIds.add(id))
    fragmentEdgeIds.forEach(id => retainedFragmentEdgeIds.add(id))
  }
  if (newNodes.length || newEdges.length) {
    networkStabilized = false
  }
  refreshVisibleCounts()
  return { newNodes, newEdges }
}

function refreshVisibleCounts() {
  if (!nodesDataSet || !edgesDataSet) return
  const nodes = nodesDataSet.get()
  const edges = edgesDataSet.get()
  visibleNodeTypeCounts.value = countBy(nodes, node => node.nodeType)
  visibleDifficultyCounts.value = countBy(
    nodes.filter(node => node.nodeType === 'Difficulty'),
    node => node.properties?.level
  )
  visibleKnowledgeSubtypeCounts.value = countBy(
    nodes.filter(node => node.nodeType === 'KnowledgeNode'),
    node => node.properties?.node_type
  )
  visibleRelationTypeCounts.value = countBy(edges, edge => edge.relationshipType)
  visibleMasteryStatusCounts.value = countBy(
    nodes.filter(node => node.nodeType === 'KnowledgeNode'),
    getNodeLearningStatus
  )
}

function handleMasteryViewChange() {
  learningState = getLearningState()
  if (nodesDataSet) {
    const highlighted = new Set(highlightedPathNodeIds.value)
    nodesDataSet.get().forEach(node => {
      if (highlighted.has(node.id)) return
      nodesDataSet.update(toGraphNodeWithMistake({
        id: node.id,
        label: node.label.replace(/\s*\(\d+错\)$/, ''), // 移除错题角标再重新计算
        type: node.nodeType,
        properties: node.properties
      }))
    })
    refreshVisibleCounts()
  }
  if (masteryViewEnabled.value) {
    router.replace({ path: route.path, query: { ...route.query, mastery: '1' } })
  } else {
    const query = { ...route.query }
    delete query.mastery
    router.replace({ path: route.path, query })
  }
}

function handleMistakeViewChange() {
  if (nodesDataSet) {
    const highlighted = new Set(highlightedPathNodeIds.value)
    nodesDataSet.get().forEach(node => {
      if (highlighted.has(node.id)) return
      nodesDataSet.update(toGraphNodeWithMistake({
        id: node.id,
        label: node.label.replace(/\s*\(\d+错\)$/, ''), // 移除旧角标
        type: node.nodeType,
        properties: node.properties
      }))
    })
    refreshVisibleCounts()
  }
}

async function refreshLearningOverlay() {
  try {
    await loadLearningState({ force: true })
    learningState = getLearningState()
    learningRevision.value = learningState.revision
    if (nodesDataSet) {
      const highlighted = new Set(highlightedPathNodeIds.value)
      nodesDataSet.get().forEach(node => {
        if (highlighted.has(node.id)) return
        nodesDataSet.update(toGraphNodeWithMistake({
          id: node.id,
          label: node.label.replace(/\s*\(\d+错\)$/, ''),
          type: node.nodeType,
          properties: node.properties
        }))
      })
      refreshVisibleCounts()
    }
  } catch (error) {
    console.error('刷新学习状态失败:', error)
  }
}

function openChapterClusters({ notify = false } = {}) {
  if (!network) return
  activeClusterIds.forEach(clusterId => {
    if (network.isCluster(clusterId)) network.openCluster(clusterId)
  })
  activeClusterIds.clear()
  clustersActive.value = false
  if (notify) ElMessage.success('已展开全部章节聚类')
}

function clusterByChapter() {
  if (!network || !nodesDataSet) return
  openChapterClusters()
  clearPathHighlight()

  const knowledgeNodes = nodesDataSet.get({
    filter: node => node.nodeType === 'KnowledgeNode' && node.properties?.chapter_id != null
  })
  const groups = new Map()
  knowledgeNodes.forEach(node => {
    const chapterId = String(node.properties.chapter_id)
    if (!groups.has(chapterId)) groups.set(chapterId, [])
    groups.get(chapterId).push(node.id)
  })

  const chapterNodes = nodesDataSet.get({ filter: node => node.nodeType === 'Chapter' })
  const chapterNames = new Map()
  chapterNodes.forEach(node => {
    const explicitOrder = node.properties?.order
    const idMatch = String(node.id || '').match(/^CHAP_(\d+)$/)
    const chapterId = explicitOrder != null ? String(explicitOrder) : (idMatch ? idMatch[1] : null)
    if (chapterId) chapterNames.set(chapterId, node.properties?.name || node.label)
  })

  groups.forEach((nodeIds, chapterId) => {
    if (nodeIds.length < 2) return
    const clusterId = `chapter-cluster:${chapterId}`
    const included = new Set(nodeIds)
    network.cluster({
      joinCondition: node => included.has(node.id),
      clusterNodeProperties: {
        id: clusterId,
        label: `${chapterNames.get(chapterId) || `第${chapterId}章`} (${nodeIds.length})`,
        title: '双击展开本章节知识点',
        shape: 'box',
        color: { background: '#e0f2fe', border: '#0284c7' },
        font: { size: 15, bold: true, color: '#0c4a6e' },
        borderWidth: 3
      }
    })
    if (network.isCluster(clusterId)) activeClusterIds.add(clusterId)
  })

  clustersActive.value = activeClusterIds.size > 0
  if (clustersActive.value) {
    network.fit({ animation: { duration: 500 } })
    ElMessage.success(`已按章节生成 ${activeClusterIds.size} 个聚类，双击可展开`)
  } else {
    ElMessage.info('当前画布没有可聚类的章节知识点')
  }
}

function toggleChapterClusters() {
  if (clustersActive.value) openChapterClusters({ notify: true })
  else clusterByChapter()
}

function clearPathHighlight() {
  if (!nodesDataSet || !edgesDataSet) return
  highlightedPathNodeIds.value.forEach(nodeId => {
    const node = nodesDataSet.get(nodeId)
    if (!node) return
    nodesDataSet.update(toGraphNode({
      id: node.id,
      label: node.properties?.name || node.label,
      type: node.nodeType,
      properties: node.properties || {}
    }))
  })
  highlightedPathEdgeIds.value.forEach(edgeId => {
    const edge = edgesDataSet.get(edgeId)
    if (!edge) return
    edgesDataSet.update({
      id: edgeId,
      width: 1.5,
      color: getRelationColor(edge.relationshipType),
      dashes: false
    })
  })
  highlightedPathNodeIds.value = []
  highlightedPathEdgeIds.value = []
  network?.unselectAll()
}

async function loadAndHighlightPath(nodeIds) {
  if (!network || !nodesDataSet || !edgesDataSet) return
  const requestedIds = [...new Set(nodeIds.map(value => String(value || '').trim()).filter(Boolean))].slice(0, 200)
  if (!requestedIds.length) return

  openChapterClusters()
  clearPathHighlight()

  const fragmentRes = await getGraphFragment(requestedIds, selectedRelTypes.value)
  if (fragmentRes.success && fragmentRes.data) mergeGraphFragment(fragmentRes.data, { retain: true })

  const foundNodes = requestedIds.filter(nodeId => Boolean(nodesDataSet.get(nodeId)))
  if (!foundNodes.length) {
    ElMessage.warning('未找到路径节点')
    return
  }

  const foundSet = new Set(foundNodes)
  const pathEdges = edgesDataSet.get({
    filter: edge => foundSet.has(edge.from) && foundSet.has(edge.to)
  })
  foundNodes.forEach(nodeId => {
    const node = nodesDataSet.get(nodeId)
    nodesDataSet.update({
      id: nodeId,
      color: {
        background: '#ffb74d',
        border: '#ea580c',
        highlight: { background: '#fdba74', border: '#c2410c' }
      },
      borderWidth: 4,
      font: { ...node.font, size: 18, bold: true }
    })
  })
  pathEdges.forEach(edge => {
    edgesDataSet.update({
      id: edge.id,
      width: 4,
      color: '#f97316',
      dashes: false
    })
  })

  highlightedPathNodeIds.value = foundNodes
  highlightedPathEdgeIds.value = pathEdges.map(edge => edge.id)
  if (!networkStabilized) await stabilizeNetwork()
  network.selectNodes(foundNodes)
  network.fit({
    nodes: foundNodes,
    animation: { duration: 800, easingFunction: 'easeInOutQuad' }
  })

  const missingCount = requestedIds.length - foundNodes.length
  if (missingCount) {
    ElMessage.warning(`已高亮 ${foundNodes.length} 个节点，${missingCount} 个节点未找到`)
  } else {
    ElMessage.success(`已高亮 ${foundNodes.length} 个路径节点和 ${pathEdges.length} 条关系`)
  }
}

// 双击节点按需展开邻居
async function handleNodeDoubleClick(params) {
  if (params.nodes.length > 0) {
    const nodeId = params.nodes[0]
    if (network?.isCluster(nodeId)) {
      network.openCluster(nodeId)
      activeClusterIds.delete(nodeId)
      clustersActive.value = activeClusterIds.size > 0
      return
    }
    await toggleNodeExpansion(nodeId)
  }
}

// 节点悬停事件
function handleNodeHover() {
  // 可以在这里添加悬停效果
}

// 搜索输入处理（防抖）
function handleSearchInput() {
  clearTimeout(searchTimer)
  showSearchHistory.value = false
  
  if (!searchNodeKeyword.value || !nodesDataSet) {
    searchResults.value = []
    showSearchResults.value = false
    showSearchHistory.value = searchHistory.value.length > 0
    return
  }
  
  searchTimer = setTimeout(() => {
    performSearch()
  }, 300)
}

function loadSearchHistory() {
  try {
    const value = JSON.parse(localStorage.getItem(SEARCH_HISTORY_KEY) || '[]')
    return Array.isArray(value) ? value.filter(item => typeof item === 'string').slice(0, SEARCH_HISTORY_LIMIT) : []
  } catch {
    return []
  }
}

function saveSearchHistory() {
  localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(searchHistory.value))
}

function addSearchHistory(keyword) {
  const normalized = String(keyword || '').trim()
  if (!normalized) return
  searchHistory.value = [
    normalized,
    ...searchHistory.value.filter(item => item !== normalized)
  ].slice(0, SEARCH_HISTORY_LIMIT)
  saveSearchHistory()
}

function removeSearchHistory(keyword) {
  searchHistory.value = searchHistory.value.filter(item => item !== keyword)
  saveSearchHistory()
  showSearchHistory.value = searchHistory.value.length > 0
}

function clearSearchHistory() {
  searchHistory.value = []
  saveSearchHistory()
  showSearchHistory.value = false
}

function handleSearchFocus() {
  if (!searchNodeKeyword.value) {
    showSearchResults.value = false
    showSearchHistory.value = searchHistory.value.length > 0
  }
}

function selectSearchHistory(keyword) {
  searchNodeKeyword.value = keyword
  showSearchHistory.value = false
  performSearch()
}

// 执行搜索
function performSearch() {
  const keyword = normalizeSearchTerm(searchNodeKeyword.value).toLowerCase()
  const nodeIds = nodesDataSet.getIds()
  const results = []
  
  for (const id of nodeIds) {
    const node = nodesDataSet.get(id)
    const props = node.properties || {}
    const name = (props.name || node.label || '').toLowerCase()
    const nodeId = (props.node_id || '').toLowerCase()
    
    if (name.includes(keyword) || nodeId.includes(keyword)) {
      results.push({
        id: id,
        name: props.name || node.label,
        type: node.nodeType || node.group,
        nodeId: props.node_id
      })
      
      if (results.length >= 10) break
    }
  }
  
  searchResults.value = results
  showSearchResults.value = results.length > 0
}

// 点击搜索结果
async function focusSearchResult(item) {
  addSearchHistory(searchNodeKeyword.value || item.name)
  await focusOnNodeWhenStable(item.id)
  showSearchResults.value = false
  searchNodeKeyword.value = item.name
  ElMessage.success(`已定位: ${item.name}`)
}

// 搜索并聚焦节点（回车触发）：本地找不到时走后端搜索并加载
async function searchAndFocusNode() {
  if (!searchNodeKeyword.value || !nodesDataSet) return

  const normalizedKeyword = normalizeSearchTerm(searchNodeKeyword.value)
  const keyword = normalizedKeyword.toLowerCase()

  // 先在已加载节点中找
  const nodeIds = nodesDataSet.getIds()
  for (const id of nodeIds) {
    const node = nodesDataSet.get(id)
    const props = node.properties || {}
    const name = (props.name || node.label || '').toLowerCase()
    const nodeId = (props.node_id || '').toLowerCase()
    if (name.includes(keyword) || nodeId.includes(keyword)) {
      await focusOnNodeWhenStable(id)
      addSearchHistory(searchNodeKeyword.value)
      showSearchResults.value = false
      ElMessage.success(`已定位: ${props.name || node.label}`)
      return
    }
  }

  // 本地没有：后端搜索（图谱默认只加载部分节点）
  try {
    const res = await searchNodes({ keyword: normalizedKeyword, limit: 5 })
    const results = Array.isArray(res.data) ? res.data : (res.data?.results || [])
    const hit = results.find(r => r.id || r.node_id)
    if (hit) {
      const ok = await locateNode(hit.id || hit.node_id)
      if (ok) {
        addSearchHistory(searchNodeKeyword.value)
        showSearchResults.value = false
        ElMessage.success(`已从数据库加载并定位: ${hit.name || hit.id}`)
        return
      }
    }
  } catch (error) {
    console.error('后端搜索节点失败:', error)
  }

  ElMessage.warning('未找到匹配的节点')
}

// 聚焦到指定节点
function focusOnNodeById(nodeId, scale = 1.5) {
  if (!network || !nodesDataSet?.get(nodeId)) return
  network.focus(nodeId, {
    scale,
    animation: {
      duration: 500,
      easingFunction: 'easeInOutQuad'
    }
  })
  network.selectNodes([nodeId])
}

function waitForNetworkStabilization() {
  if (!network || networkStabilized) return Promise.resolve()
  return new Promise(resolve => network.once('stabilizationIterationsDone', resolve))
}

function stabilizeNetwork() {
  if (!network) return Promise.resolve()
  networkStabilized = false
  const currentNetwork = network
  return new Promise(resolve => {
    currentNetwork.once('stabilizationIterationsDone', resolve)
    currentNetwork.stabilize()
  })
}

async function focusOnNodeWhenStable(nodeId, scale = 1.5) {
  await waitForNetworkStabilization()
  focusOnNodeById(nodeId, scale)
}

// 在画布中定位业务节点：本地找不到时从后端拉节点与邻居后再定位
async function locateNode(focusId) {
  const target = resolveCanonicalGraphTarget(focusId)
  const localId = nodesDataSet.getIds().find(id => {
    const node = nodesDataSet.get(id)
    const props = node.properties || {}
    return id === target || props.node_id === target || props.name === target
  })
  if (localId) {
    await focusOnNodeWhenStable(localId)
    return true
  }

  const detailRes = await getNodeDetail(target, 'both')
  if (!detailRes.success || !detailRes.data?.node) return false
  const node = detailRes.data.node
  if (!nodesDataSet.get(node.id)) {
    nodesDataSet.add(toGraphNodeWithMistake(node))
    // 导航加载的节点标记为保留，不会被后续的"折叠邻居"操作删除
    retainedFragmentNodeIds.add(node.id)
    networkStabilized = false
  }
  // 邻居也用 retain:true，与"打开相关节点"保持一致：
  // 这样用户手动点"展开邻居"才算可折叠的操作，
  // locateNode 带来的初始邻居不会在折叠时消失
  const neighborRes = await getNodeNeighbors(node.id, 30, selectedRelTypes.value)
  if (neighborRes.success && neighborRes.data) {
    mergeGraphFragment(neighborRes.data, { retain: true })
  }
  await focusOnNodeWhenStable(node.id)
  return true
}

async function openRelatedNode(row) {
  const node = row?.target
  if (!node?.id) {
    ElMessage.warning('目标节点缺少业务 ID，无法打开')
    return
  }

  if (node.label === 'Question') {
    showNodeDetail.value = false
    await router.push({ path: '/questions', query: { id: node.id } })
    return
  }

  try {
    if (!nodesDataSet.get(node.id)) {
      const relationshipType = row.relationship?.type
      const res = await getNodeNeighbors(
        selectedNode.value.id,
        100,
        relationshipType ? [relationshipType] : []
      )
      if (res.success && res.data) mergeGraphFragment(res.data, { retain: true })
    }

    if (!nodesDataSet.get(node.id)) {
      nodesDataSet.add(toGraphNode({
        id: node.id,
        label: node.name || node.label,
        type: node.label,
        properties: node.properties || {}
      }))
      retainedFragmentNodeIds.add(node.id)
      networkStabilized = false
    }

    if (!networkStabilized) await stabilizeNetwork()
    if (!nodesDataSet.get(node.id)) throw new Error(`Node ${node.id} was not added`)
    focusOnNodeById(node.id)
    showNodeDetail.value = false
  } catch (error) {
    console.error('打开相关节点失败:', error)
    ElMessage.error('目标节点加载失败，请稍后重试')
  }
}

// 适应屏幕
function fitToScreen() {
  if (!network) return
  network.fit({
    animation: {
      duration: 500,
      easingFunction: 'easeInOutQuad'
    }
  })
}

async function reloadGraph() {
  if (nodesDataSet) nodesDataSet.clear()
  if (edgesDataSet) edgesDataSet.clear()
  await loadGraphData()
}

async function restoreDefaultView() {
  showNodeDetail.value = false
  searchResults.value = []
  showSearchResults.value = false
  await reloadGraph()
  ElMessage.success('已恢复默认图谱视图')
}

function downloadPngBlob(blob) {
  if (!blob) {
    ElMessage.error('图谱图片生成失败')
    return
  }
  const link = document.createElement('a')
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
  const url = URL.createObjectURL(blob)
  link.href = url
  link.download = `knowledge-graph-${timestamp}.png`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
  ElMessage.success('图谱 PNG 已导出')
}

function exportGraphAsPng() {
  const sourceCanvas = graphContainer.value?.querySelector('canvas')
  if (!sourceCanvas || !sourceCanvas.width || !sourceCanvas.height) {
    ElMessage.warning('图谱尚未完成渲染')
    return
  }

  network?.redraw()
  const outputCanvas = document.createElement('canvas')
  outputCanvas.width = sourceCanvas.width
  outputCanvas.height = sourceCanvas.height
  const context = outputCanvas.getContext('2d')
  if (!context) {
    ElMessage.error('当前浏览器不支持图片导出')
    return
  }
  context.fillStyle = '#f5f7fa'
  context.fillRect(0, 0, outputCanvas.width, outputCanvas.height)
  context.drawImage(sourceCanvas, 0, 0)
  outputCanvas.toBlob(downloadPngBlob, 'image/png')
}

// 应用筛选
function applyFilter() {
  showNodeFilter.value = false
  reloadGraph()
}

// 获取节点详情按钮文本
function getNodeDetailButtonText() {
  const node = selectedNode.value
  
  // 题目节点
  if (node.label === 'Question') {
    return '查看题目详情'
  }
  
  // 知识点节点
  if (node.label === 'KnowledgeNode') {
    return '查看知识点详情'
  }
  
  // 章节节点
  if (node.label === 'Chapter') {
    return '查看章节内容'
  }
  
  return '查看详情'
}

// 根据节点类型跳转到不同页面
function viewNodeDetail() {
  const node = selectedNode.value
  
  // 题目节点 -> 跳转题目页面
  if (node.label === 'Question') {
    router.push({
      path: '/questions',
      query: { id: node.node_id || node.id }
    })
    showNodeDetail.value = false
    return
  }
  
  // 知识点节点 -> 跳转知识点页面
  if (node.label === 'KnowledgeNode') {
    router.push({
      path: '/knowledge',
      query: { focus: node.node_id || node.name }
    })
    showNodeDetail.value = false
    return
  }
  
  // 章节节点 -> 跳转知识点页面并筛选章节
  if (node.label === 'Chapter') {
    const explicitOrder = Number(node.order)
    const idMatch = String(node.id || '').match(/^CHAP_(\d+)$/)
    const chapterId = Number.isInteger(explicitOrder) && explicitOrder > 0
      ? explicitOrder
      : (idMatch ? Number(idMatch[1]) : null)

    router.push({
      path: '/knowledge',
      query: chapterId
        ? { chapter_id: chapterId }
        : { section: node.name }
    })
    showNodeDetail.value = false
    return
  }
  
  // 其他节点 - 显示提示
  ElMessage.info('该节点暂无详情页面')
}

onMounted(async () => {
  showLegend.value = window.innerWidth > 900
  // 点击外部关闭搜索结果
  document.addEventListener('click', handleClickOutside)

  await refreshLearningOverlay()
  window.addEventListener('focus', refreshLearningOverlay)
  await initGraph()

  // 检查URL参数，跳转到指定节点
  const focusNodeId = route.query.focus
  const highlightNodeIds = route.query.highlight

  if (focusNodeId) {
    try {
      await waitForNetworkStabilization()
      const ok = await locateNode(focusNodeId)
      if (ok) {
        ElMessage.success(`已定位到节点: ${focusNodeId}`)
      } else {
        ElMessage.warning('未找到指定节点')
      }
    } catch (error) {
      console.error('跳转到节点失败:', error)
      ElMessage.error('跳转到节点失败')
    }
  }

  // 处理高亮多个节点（来自学习路径页面）
  if (highlightNodeIds) {
    const idsToHighlight = String(highlightNodeIds).split(',')
    try {
      await waitForNetworkStabilization()
      await loadAndHighlightPath(idsToHighlight)
    } catch (error) {
      console.error('高亮节点失败:', error)
      ElMessage.error('高亮节点失败')
    }
  }
})

onUnmounted(() => {
  destroyNetwork()
  clearTimeout(searchTimer)
  document.removeEventListener('click', handleClickOutside)
  window.removeEventListener('focus', refreshLearningOverlay)
})

// 点击外部关闭搜索结果
function handleClickOutside(e) {
  if (!e.target.closest('.header-actions')) {
    showSearchResults.value = false
    showSearchHistory.value = false
  }
}
</script>

<style scoped>
.graph-page {
  height: calc(100vh - 60px - 60px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.graph-header {
  flex: 0 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 15px 20px;
  background: white;
  border-bottom: 1px solid #ebeef5;
}

.graph-header .title {
  font-size: 18px;
  font-weight: bold;
  color: #303133;
  flex: 0 0 auto;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  position: relative;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.graph-search-input {
  width: 200px;
  margin-right: 10px;
}

.header-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.search-results-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  width: 250px;
  max-height: 300px;
  overflow-y: auto;
  background: white;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  z-index: 100;
  margin-top: 5px;
}

.search-result-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
  transition: background 0.2s;
  border-bottom: 1px solid #f0f0f0;
}

.search-result-item:last-child {
  border-bottom: none;
}

.search-result-item:hover {
  background: #f5f7fa;
}

.search-result-item .result-name {
  font-size: 13px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 8px;
}

.search-history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  font-size: 12px;
  color: #606266;
  border-bottom: 1px solid #ebeef5;
}

.history-item {
  gap: 8px;
}

.history-icon {
  flex: 0 0 auto;
  color: #909399;
}

.graph-container-wrapper {
  flex: 1;
  position: relative;
  overflow: hidden;
}

#graph-container {
  height: 100%;
  width: 100%;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e7ed 100%);
}

.legend-panel {
  position: absolute;
  top: 20px;
  right: 20px;
  background: white;
  padding: 15px;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  width: 200px;
  max-width: calc(100% - 40px);
  max-height: calc(100% - 110px);
  overflow-y: auto;
}

.legend-panel.is-collapsed {
  width: auto;
  padding: 8px 10px;
  overflow: visible;
}

.legend-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 24px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.legend-content {
  padding-top: 10px;
}

.legend-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}

.legend-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #606266;
}

.legend-color {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  box-sizing: border-box;
  flex: 0 0 16px;
}

.legend-line {
  width: 20px;
  height: 3px;
  border-radius: 2px;
}

.legend-label {
  flex: 1;
  min-width: 0;
}

.legend-count {
  min-width: 24px;
  text-align: right;
  color: #909399;
  font-variant-numeric: tabular-nums;
}

.legend-divider {
  height: 1px;
  background: #ebeef5;
  margin: 12px 0;
}

.legend-note {
  font-size: 11px;
  color: #909399;
  line-height: 1.5;
  margin-top: 8px;
  padding: 6px 8px;
  background: #fef0f0;
  border-radius: 4px;
  border-left: 3px solid #f56c6c;
}

.legend-mistake-marker {
  background: #409eff;
  border: 3px dashed #9333ea;
  box-sizing: border-box;
}

.mistake-toggle {
  margin-left: 12px;
}

:deep(.el-drawer__body) {
  padding: 20px;
}

.node-detail-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-section h4 {
  margin: 0 0 10px 0;
  font-size: 14px;
  color: #303133;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
}

.overview-text {
  font-size: 14px;
  line-height: 1.6;
  color: #606266;
  margin: 0;
}

.tags-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

:deep(.node-tag) {
  max-width: 100%;
  height: auto;
  min-height: 24px;
  line-height: 1.45;
  white-space: normal;
  overflow-wrap: anywhere;
}

.detail-actions {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}

:deep(.el-dialog) {
  max-width: calc(100vw - 24px);
}

:deep(.el-drawer) {
  max-width: 100%;
}

@media (max-width: 900px) {
  .graph-header {
    align-items: flex-start;
    padding: 10px 12px;
  }

  .graph-header .title,
  .header-actions {
    width: 100%;
  }

  .header-actions {
    justify-content: flex-start;
    gap: 8px;
  }

  .graph-search-input {
    flex: 1 1 200px;
    width: auto;
    min-width: 180px;
    margin-right: 0;
  }

  .search-results-dropdown {
    top: 36px;
    width: min(280px, calc(100vw - 24px));
  }

  .legend-panel {
    top: 10px;
    right: 10px;
    width: 190px;
    max-width: calc(100% - 20px);
    max-height: calc(100% - 90px);
  }

  .legend-panel.is-collapsed {
    width: auto;
  }

  .detail-actions {
    flex-wrap: wrap;
  }
}
</style>
