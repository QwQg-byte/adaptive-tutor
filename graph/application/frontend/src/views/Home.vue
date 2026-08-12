<template>
  <div class="home">
    <!-- 欢迎区域 -->
    <div class="welcome-section">
      <div class="welcome-content">
        <h1>程序设计大赛中的知识图谱</h1>
        <p>基于知识图谱的算法学习平台，包含 {{ homeData.overview.total_questions }} 道精选题目和 {{ homeData.overview.total_knowledge_points }} 个知识点</p>
        <div class="quick-actions">
          <el-button type="primary" size="large" @click="$router.push({ path: '/questions', query: { sort_by: 'difficulty' } })">
            <el-icon><EditPen /></el-icon>
            开始练习
          </el-button>
          <el-button size="large" @click="$router.push('/knowledge')">
            <el-icon><Reading /></el-icon>
            浏览知识点
          </el-button>
          <el-button size="large" @click="$router.push('/graph')">
            <el-icon><Share /></el-icon>
            查看图谱
          </el-button>
        </div>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-section">
      <div class="stat-card" v-for="stat in statistics" :key="stat.label">
        <div class="stat-icon" :style="{ background: stat.gradient }">
          <el-icon :size="28"><component :is="stat.icon" /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stat.value }}</div>
          <div class="stat-label">{{ stat.label }}</div>
        </div>
      </div>
    </div>

    <!-- 功能入口 -->
    <div class="features-section">
      <div class="feature-item" @click="$router.push('/graph')">
        <div class="feature-icon" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
          <el-icon :size="24" color="white"><Share /></el-icon>
        </div>
        <span class="feature-title">图谱浏览</span>
        <span class="feature-desc">可视化知识图谱</span>
      </div>
      <div class="feature-item" @click="$router.push('/knowledge')">
        <div class="feature-icon" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
          <el-icon :size="24" color="white"><Reading /></el-icon>
        </div>
        <span class="feature-title">知识浏览</span>
        <span class="feature-desc">探索知识点体系</span>
      </div>
      <div class="feature-item" @click="$router.push('/search')">
        <div class="feature-icon" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
          <el-icon :size="24" color="white"><Search /></el-icon>
        </div>
        <span class="feature-title">智能搜索</span>
        <span class="feature-desc">快速定位内容</span>
      </div>
      <div class="feature-item" @click="$router.push('/path')">
        <div class="feature-icon" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
          <el-icon :size="24" color="white"><Guide /></el-icon>
        </div>
        <span class="feature-title">学习路径</span>
        <span class="feature-desc">知识点学习路径规划</span>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="main-content">
      <!-- 左侧：热门知识点 + 难度分布 -->
      <div class="left-section">
        <!-- 热门知识点 -->
        <el-card class="section-card hot-kp-card">
          <template #header>
            <div class="card-header">
              <span><el-icon><TrendCharts /></el-icon> 热门知识点</span>
              <el-tag size="small" type="info">TOP 10</el-tag>
            </div>
          </template>
          <div class="hot-kp-list">
            <div 
              class="hot-kp-item" 
              v-for="(kp, index) in homeData.hot_knowledge_points" 
              :key="kp.id"
              @click="goToKnowledge(kp.id)"
            >
              <div class="kp-rank" :class="'rank-' + (index + 1)">{{ index + 1 }}</div>
              <div class="kp-info">
                <div class="kp-name">{{ kp.name }}</div>
                <div class="kp-count">{{ kp.question_count }} 道题</div>
              </div>
              <el-progress 
                :percentage="getPercentage(kp.question_count, homeData.overview.total_questions)" 
                :stroke-width="6"
                :show-text="false"
              />
            </div>
          </div>
        </el-card>

        <!-- 难度分布 -->
        <el-card class="section-card difficulty-card">
          <template #header>
            <div class="card-header">
              <span><el-icon><PieChart /></el-icon> 难度分布</span>
            </div>
          </template>
          <div class="difficulty-list">
            <div 
              class="difficulty-item" 
              v-for="diff in homeData.difficulty_stats" 
              :key="diff.difficulty"
            >
              <div class="diff-info">
                <el-tag :type="getDifficultyType(diff.difficulty)" size="small">
                  {{ diff.difficulty || '未分类' }}
                </el-tag>
                <span class="diff-count">{{ diff.count }} 题</span>
              </div>
              <el-progress 
                :percentage="getPercentage(diff.count, homeData.overview.total_questions)"
                :stroke-width="10"
                :color="getDifficultyColor(diff.difficulty)"
              />
            </div>
          </div>
        </el-card>
      </div>

      <!-- 右侧：推荐题目 + 分类统计 -->
      <div class="right-section">
        <!-- 推荐题目 -->
        <el-card class="section-card recommend-card">
          <template #header>
            <div class="card-header">
              <span><el-icon><Star /></el-icon> 推荐题目</span>
              <el-button text type="primary" @click="$router.push({ path: '/questions', query: { sort_by: 'difficulty' } })">
                查看更多 <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
          </template>
          <div class="recommend-list">
            <div 
              class="recommend-item" 
              v-for="q in homeData.recommended_questions" 
              :key="q.id"
              @click="goToQuestion(q)"
            >
              <div class="q-info">
                <div class="q-id">{{ q.id }}</div>
                <div class="q-name">{{ q.name }}</div>
              </div>
              <div class="q-meta">
                <el-tag :type="getDifficultyType(q.difficulty)" size="small">
                  {{ q.difficulty || '中等' }}
                </el-tag>
                <span class="q-category">{{ q.category1 }}</span>
              </div>
            </div>
          </div>
        </el-card>

        <!-- 分类统计 -->
        <el-card class="section-card category-card">
          <template #header>
            <div class="card-header">
              <span><el-icon><Grid /></el-icon> 题目分类</span>
            </div>
          </template>
          <div class="category-grid">
            <div 
              class="category-item" 
              v-for="cat in homeData.category_stats" 
              :key="cat.category"
              @click="goToCategory(cat.category)"
            >
              <div class="cat-name">{{ cat.category }}</div>
              <div class="cat-count">{{ cat.count }}</div>
            </div>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, markRaw } from 'vue'
import { useRouter } from 'vue-router'
import { getHomeData } from '@/api/graph'
import {
  Share, Search, Guide, Reading, EditPen, TrendCharts, PieChart, Star, ArrowRight, Grid,
  DataAnalysis, Collection, Connection
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const router = useRouter()

const statistics = ref([
  { label: '算法题目', value: 0, icon: markRaw(EditPen), gradient: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' },
  { label: '知识点', value: 0, icon: markRaw(DataAnalysis), gradient: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)' },
  { label: '章节', value: 0, icon: markRaw(Collection), gradient: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)' },
  { label: '知识关联', value: 0, icon: markRaw(Connection), gradient: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)' }
])

const homeData = reactive({
  overview: {
    total_questions: 0,
    total_knowledge_points: 0,
    total_chapters: 0,
    total_relationships: 0
  },
  difficulty_stats: [],
  category_stats: [],
  hot_knowledge_points: [],
  recommended_questions: []
})

// 获取百分比
const getPercentage = (value, total) => {
  if (!total) return 0
  return Math.round((value / total) * 100)
}

// 获取难度颜色
const getDifficultyColor = (difficulty) => {
  const colors = {
    '简单': '#67c23a',
    '中等': '#e6a23c',
    '困难': '#f56c6c'
  }
  return colors[difficulty] || '#909399'
}

// 获取难度标签类型
const getDifficultyType = (difficulty) => {
  const types = {
    '简单': 'success',
    '中等': 'warning',
    '困难': 'danger'
  }
  return types[difficulty] || 'info'
}

// 跳转到知识点（知识页通过 focus 参数定位节点）
const goToKnowledge = (kpId) => {
  router.push({ path: '/knowledge', query: { focus: kpId } })
}

// 跳转到题目
const goToQuestion = (q) => {
  if (q.url) {
    window.open(q.url, '_blank')
  } else {
    router.push('/questions')
  }
}

// 跳转到分类
const goToCategory = (category) => {
  router.push({ path: '/questions', query: { category1: category } })
}

onMounted(async () => {
  try {
    const res = await getHomeData()
    if (res.success && res.data) {
      const data = res.data
      
      // 更新概览数据
      homeData.overview = data.overview
      homeData.difficulty_stats = data.difficulty_stats || []
      homeData.category_stats = data.category_stats || []
      homeData.hot_knowledge_points = data.hot_knowledge_points || []
      homeData.recommended_questions = data.recommended_questions || []
      
      // 更新统计卡片
      statistics.value[0].value = data.overview.total_questions
      statistics.value[1].value = data.overview.total_knowledge_points
      statistics.value[2].value = data.overview.total_chapters
      statistics.value[3].value = data.overview.total_relationships
    }
  } catch (error) {
    console.error('获取首页数据失败:', error)
    ElMessage.error('获取数据失败，请检查后端服务')
  }
})
</script>

<style scoped>
.home {
  min-height: calc(100vh - 60px);
  background: #f5f7fa;
  overflow-y: auto;
}

/* 欢迎区域 */
.welcome-section {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 40px 20px;
  color: white;
}

.welcome-content {
  max-width: 1200px;
  margin: 0 auto;
  text-align: center;
}

.welcome-content h1 {
  font-size: 32px;
  margin: 0 0 12px 0;
  font-weight: 600;
}

.welcome-content p {
  font-size: 16px;
  opacity: 0.9;
  margin: 0 0 24px 0;
}

.quick-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}

/* 统计卡片 */
.stats-section {
  display: flex;
  gap: 20px;
  padding: 20px;
  max-width: 1200px;
  margin: -30px auto 0;
  position: relative;
  z-index: 10;
}

.stat-card {
  flex: 1;
  background: white;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  transition: transform 0.3s, box-shadow 0.3s;
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12);
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.stat-value {
  font-size: 28px;
  font-weight: 600;
  color: #303133;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 4px;
}

/* 主内容区 */
.main-content {
  display: flex;
  gap: 20px;
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.left-section, .right-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section-card {
  border-radius: 12px;
}

.section-card :deep(.el-card__header) {
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  color: #303133;
}

.card-header .el-icon {
  margin-right: 8px;
  vertical-align: middle;
}

/* 热门知识点 */
.hot-kp-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.hot-kp-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.hot-kp-item:hover {
  background: #f5f7fa;
}

.kp-rank {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #909399;
  background: #f0f2f5;
}

.kp-rank.rank-1 { background: #ffd700; color: white; }
.kp-rank.rank-2 { background: #c0c0c0; color: white; }
.kp-rank.rank-3 { background: #cd7f32; color: white; }

.kp-info {
  flex: 1;
  min-width: 0;
}

.kp-name {
  font-size: 14px;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kp-count {
  font-size: 12px;
  color: #909399;
}

.hot-kp-item .el-progress {
  width: 80px;
}

/* 难度分布 */
.difficulty-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.difficulty-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.diff-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.diff-count {
  font-size: 14px;
  color: #606266;
}

/* 推荐题目 */
.recommend-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.recommend-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-radius: 8px;
  background: #f5f7fa;
  cursor: pointer;
  transition: background 0.2s;
}

.recommend-item:hover {
  background: #e8eaed;
}

.q-info {
  flex: 1;
  min-width: 0;
}

.q-id {
  font-size: 12px;
  color: #909399;
}

.q-name {
  font-size: 14px;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.q-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.q-category {
  font-size: 12px;
  color: #909399;
}

/* 分类统计 */
.category-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.category-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-radius: 8px;
  background: #f5f7fa;
  cursor: pointer;
  transition: background 0.2s;
}

.category-item:hover {
  background: #e8eaed;
}

.cat-name {
  font-size: 13px;
  color: #303133;
}

.cat-count {
  font-size: 14px;
  font-weight: 600;
  color: #409eff;
}

/* 功能入口 */
.features-section {
  display: flex;
  gap: 16px;
  padding: 0 20px;
  max-width: 1200px;
  margin: 20px auto;
}

.feature-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px 16px;
  background: white;
  border-radius: 12px;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.feature-item:hover {
  transform: translateY(-4px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
}

.feature-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.feature-title {
  font-size: 15px;
  color: #303133;
  font-weight: 600;
}

.feature-desc {
  font-size: 12px;
  color: #909399;
}

/* 响应式 */
@media (max-width: 900px) {
  .main-content {
    flex-direction: column;
  }
  
  .stats-section {
    flex-wrap: wrap;
  }
  
  .stat-card {
    flex: 1 1 calc(50% - 10px);
    min-width: 150px;
  }
  
  .features-section {
    flex-wrap: wrap;
  }
  
  .feature-item {
    flex: 1 1 calc(50% - 8px);
    min-width: 140px;
  }
}
</style>
