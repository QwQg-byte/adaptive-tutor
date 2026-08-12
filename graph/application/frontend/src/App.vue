<template>
  <div id="app">
    <el-container>
      <!-- 顶部导航 -->
      <el-header>
        <div class="header-content">
          <h1 class="logo">📊 知识图谱可视化系统</h1>
          <el-menu
            mode="horizontal"
            :default-active="activeMenu"
            router
            class="nav-menu"
          >
            <el-menu-item index="/">
              <span>首页</span>
            </el-menu-item>
            <el-menu-item index="/graph">
              <span>图谱浏览</span>
            </el-menu-item>
            <el-menu-item index="/dashboard">
              <span>学习总览</span>
            </el-menu-item>
            <el-menu-item index="/knowledge">
              <span>知识浏览</span>
            </el-menu-item>
            <el-menu-item index="/questions" @click="goToQuestions">
              <span>算法题目</span>
            </el-menu-item>
            <el-menu-item index="/mistakes">
              <span>错题本</span>
            </el-menu-item>
            <el-menu-item index="/search">
              <span>智能搜索</span>
            </el-menu-item>
            <el-menu-item index="/path">
              <span>学习路径</span>
            </el-menu-item>
          </el-menu>
          <el-link class="tutor-link" :underline="false" @click="goToTutor">
            伴学 Agent
          </el-link>
        </div>
      </el-header>

      <!-- 主内容区 -->
      <el-main :class="{ 'no-padding': usesFullBleedMain }">
        <router-view />
      </el-main>

      <!-- 底部 -->
      <el-footer>
        <p>&copy; 2026 知识图谱可视化系统 | Powered by Vue 3 + Neo4j</p>
      </el-footer>
    </el-container>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getStudentId } from '@/api/learner'
import {
  legacyMigrationPending,
  loadLearningState,
  migrateLegacyLearningState
} from '@/stores/progress'

const route = useRoute()
const router = useRouter()

const activeMenu = computed(() => route.path)
const usesFullBleedMain = computed(() => ['/', '/graph'].includes(route.path))

// 跳转到题目页面，默认按难度排序
function goToQuestions() {
  router.push({ path: '/questions', query: { sort_by: 'difficulty' } })
}

function goToTutor() {
  const configuredUrl = import.meta.env.VITE_TUTOR_URL
  const tutorUrl = configuredUrl || (import.meta.env.DEV ? 'http://127.0.0.1:8600/' : '/tutor/')
  const target = new URL(tutorUrl, window.location.origin)
  target.searchParams.set('student', getStudentId())
  window.location.assign(target.toString())
}

function refreshOnFocus() {
  loadLearningState({ force: true }).catch(error => {
    console.error('刷新学习状态失败:', error)
  })
}

function reportCount(values = {}) {
  return Object.values(values).reduce((sum, value) => sum + Number(value || 0), 0)
}

onMounted(async () => {
  window.addEventListener('focus', refreshOnFocus)
  try {
    await loadLearningState()
    if (!legacyMigrationPending()) return
    const preview = await migrateLegacyLearningState({ preview: true })
    const pendingCount = reportCount(preview?.summary)
    await ElMessageBox.confirm(
      `检测到当前浏览器中的 ${pendingCount} 项旧学习记录，是否导入统一学习档案？`,
      '迁移学习记录',
      {
        confirmButtonText: '导入',
        cancelButtonText: '暂不导入',
        type: 'info'
      }
    )
    const report = await migrateLegacyLearningState()
    const imported = reportCount(report?.imported)
    const skipped = reportCount(report?.skipped)
    const conflicts = Number(report?.conflicts || 0)
    ElMessage.success(`已导入 ${imported} 项，跳过 ${skipped} 项，发现 ${conflicts} 项证据冲突`)
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    console.error('初始化学习状态失败:', error)
    ElMessage.warning('学习状态服务暂时不可用')
  }
})

onUnmounted(() => window.removeEventListener('focus', refreshOnFocus))
</script>

<style scoped>
#app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.el-container {
  min-height: 100vh;
}

.el-header {
  background-color: #409eff;
  color: white;
  display: flex;
  align-items: center;
  padding: 0 20px;
}

.header-content {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logo {
  margin: 0;
  font-size: 24px;
  font-weight: bold;
  white-space: nowrap;
}

.nav-menu {
  border: none;
  background: transparent;
  flex: 1;
  margin-left: 40px;
}

.nav-menu .el-menu-item {
  color: rgba(255, 255, 255, 0.9);
}

.nav-menu .el-menu-item:hover {
  background-color: rgba(255, 255, 255, 0.1);
}

.nav-menu .el-menu-item.is-active {
  background-color: rgba(255, 255, 255, 0.2);
}

.tutor-link {
  flex: 0 0 auto;
  color: white;
  font-size: 14px;
  white-space: nowrap;
}

.el-main {
  flex: 1;
  padding: 20px;
  background-color: #f5f7fa;
  overflow: hidden;
}

/* 首页和图谱页无padding */
.el-main.no-padding {
  padding: 0;
}

.el-footer {
  background-color: #303133;
  color: #909399;
  text-align: center;
  padding: 20px;
}

.el-footer p {
  margin: 0;
}

@media (max-width: 900px) {
  .el-header {
    padding: 0 10px;
  }

  .logo {
    display: none;
  }

  .nav-menu {
    width: 100%;
    margin-left: 0;
    overflow-x: auto;
    overflow-y: hidden;
    scrollbar-width: none;
  }

  .nav-menu::-webkit-scrollbar {
    display: none;
  }

  .nav-menu .el-menu-item {
    flex: 0 0 auto;
    padding: 0 14px;
  }

  .tutor-link {
    margin-left: 10px;
  }

  .el-main {
    padding: 12px;
  }

  .el-footer {
    padding: 12px;
    font-size: 12px;
  }
}
</style>
