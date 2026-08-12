<template>
  <el-card class="knowledge-list-card">
    <template #header>
      <div class="card-header"><span>知识点列表</span></div>
      <div class="header-controls">
        <el-select
          :model-value="chapterId"
          size="small"
          placeholder="章节筛选"
          clearable
          @update:model-value="$emit('update:chapter-id', $event)"
        >
          <el-option label="全部章节" value="" />
          <el-option-group
            v-for="group in groupedChapters"
            :key="group.id"
            :label="group.name"
          >
            <el-option
              v-for="chapter in group.chapters"
              :key="chapter.id"
              :label="chapter.name"
              :value="chapter.id"
            />
          </el-option-group>
        </el-select>
        <el-select
          :model-value="knowledgeType"
          size="small"
          placeholder="类型筛选"
          clearable
          @update:model-value="$emit('update:knowledge-type', $event)"
        >
          <el-option label="全部类型" value="" />
          <el-option label="核心抽象" value="核心抽象" />
          <el-option label="核心实体" value="核心实体" />
          <el-option label="关键事件" value="关键事件" />
        </el-select>
        <el-input
          :model-value="keyword"
          placeholder="搜索知识点..."
          clearable
          size="small"
          @update:model-value="$emit('update:keyword', $event)"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
    </template>

    <div v-loading="loading" class="knowledge-list">
      <button
        v-for="item in items"
        :key="item.id"
        type="button"
        class="knowledge-item"
        :class="{ active: selectedId === item.id }"
        @click="$emit('select', item)"
      >
        <span class="kp-header">
          <el-tag size="small" :type="tagType(item.node_type)">{{ item.node_type || '知识点' }}</el-tag>
          <span class="kp-id">{{ item.node_id }}</span>
        </span>
        <span class="kp-name">{{ item.name }}</span>
        <span v-if="item.section" class="kp-section">{{ item.section }}</span>
      </button>
      <el-empty v-if="!loading && items.length === 0" description="暂无知识点" :image-size="80" />
    </div>

    <div class="list-footer">
      <span>共 {{ total }} 个知识点</span>
      <el-pagination
        small
        background
        layout="prev, pager, next"
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        @current-change="$emit('page-change', $event)"
      />
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import { Search } from '@element-plus/icons-vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  chapters: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
  chapterId: { type: [String, Number], default: '' },
  knowledgeType: { type: String, default: '' },
  keyword: { type: String, default: '' },
  loading: Boolean,
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 30 },
  total: { type: Number, default: 0 }
})

const groupedChapters = computed(() => {
  const groups = new Map()
  props.chapters.forEach(chapter => {
    const id = chapter.course_id || 'unknown'
    if (!groups.has(id)) {
      groups.set(id, {
        id,
        name: chapter.course_name || '未分类课程',
        chapters: []
      })
    }
    groups.get(id).chapters.push(chapter)
  })
  return [...groups.values()]
})

defineEmits(['select', 'page-change', 'update:chapter-id', 'update:knowledge-type', 'update:keyword'])

function tagType(type) {
  return { '核心抽象': 'primary', '核心实体': 'success', '关键事件': 'warning' }[type] || 'info'
}
</script>

<style scoped>
.knowledge-list-card { height: 100%; max-height: calc(100vh - 140px); display: flex; flex-direction: column; overflow: hidden; }
.knowledge-list-card :deep(.el-card__body) { flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 15px; }
.knowledge-list-card :deep(.el-card__header) { padding: 15px; }
.card-header { font-weight: 600; margin-bottom: 10px; }
.header-controls { display: grid; gap: 10px; }
.knowledge-list { flex: 1; min-height: 180px; overflow-y: auto; padding: 10px 4px; }
.knowledge-item { display: block; width: 100%; padding: 12px; margin-bottom: 8px; text-align: left; background: white; border: 1px solid #ebeef5; border-radius: 6px; cursor: pointer; }
.knowledge-item:hover, .knowledge-item.active { border-color: #409eff; background: #ecf5ff; }
.kp-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.kp-id { font-size: 12px; color: #909399; font-family: monospace; }
.kp-name, .kp-section { display: block; }
.kp-name { font-weight: 600; font-size: 14px; color: #303133; }
.kp-section { margin-top: 4px; font-size: 12px; color: #909399; }
.list-footer { display: grid; justify-items: center; gap: 8px; padding-top: 10px; font-size: 12px; color: #909399; border-top: 1px solid #ebeef5; }
</style>
