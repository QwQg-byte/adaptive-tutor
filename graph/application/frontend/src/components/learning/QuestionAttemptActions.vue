<template>
  <div class="attempt-panel">
    <span class="attempt-label">本次作答</span>
    <div class="attempt-buttons">
      <el-button
        data-testid="record-wrong"
        type="danger"
        plain
        :disabled="disabled || loading || !questionId"
        @click="recordAttempt(false)"
      >
        <el-icon><CircleClose /></el-icon>
        做错了
      </el-button>
      <el-button
        data-testid="record-correct"
        type="success"
        :disabled="disabled || loading || !questionId"
        @click="recordAttempt(true)"
      >
        <el-icon><CircleCheck /></el-icon>
        做对了
      </el-button>
    </div>
    <span v-if="attempt" class="attempt-status" :class="{ unresolved: attempt.unresolved }">
      {{ attempt.unresolved ? '待复习' : '已解决' }}，累计错 {{ attempt.wrong_count }} 次
    </span>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheck, CircleClose } from '@element-plus/icons-vue'
import { getMistake, loadLearningState } from '@/stores/progress'
import { learnerErrorMessage } from '@/api/learner'
import { recordQuestionResult } from '@/utils/questionAttempts'

const props = defineProps({
  questionId: { type: String, default: '' },
  knowledgePoints: { type: Array, default: () => [] },
  disabled: Boolean
})

const emit = defineEmits(['recorded'])
const attempt = ref(null)
const loading = ref(false)

function refreshAttempt() {
  attempt.value = getMistake(props.questionId)
}

async function recordAttempt(correct) {
  loading.value = true
  try {
    await recordQuestionResult(props.questionId, props.knowledgePoints, correct)
    attempt.value = getMistake(props.questionId)
    ElMessage({
      type: correct ? 'success' : 'warning',
      message: correct ? '已记录为做对，相关错题已解决' : '已加入错题本'
    })
    emit('recorded', attempt.value)
  } catch (error) {
    ElMessage.error(learnerErrorMessage(error, '记录作答失败，请刷新后重试'))
  } finally {
    loading.value = false
  }
}

watch(() => props.questionId, async () => {
  try {
    await loadLearningState()
  } finally {
    refreshAttempt()
  }
}, { immediate: true })
</script>

<style scoped>
.attempt-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 12px;
}

.attempt-label,
.attempt-status {
  font-size: 13px;
  color: #606266;
}

.attempt-buttons {
  display: flex;
  gap: 8px;
}

.attempt-buttons :deep(.el-button + .el-button) {
  margin-left: 0;
}

.attempt-status {
  color: #67c23a;
}

.attempt-status.unresolved {
  color: #f56c6c;
}
</style>
