<template>
  <div class="path-page">
    <!-- 顶部标题栏 -->
    <div class="page-header">
      <div class="header-left">
        <el-icon :size="24"><Guide /></el-icon>
        <h2>学习路径</h2>
        <el-radio-group v-model="activeMode" size="small" class="mode-switch">
          <el-radio-button value="plan">学习计划</el-radio-button>
          <el-radio-button value="learning">学习路径规划</el-radio-button>
          <el-radio-button value="shortest">路径查找</el-radio-button>
          <el-radio-button value="dependency">依赖分析</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- 主体区域 -->
    <div class="main-area">
      <!-- 左侧控制面板 -->
      <div class="control-panel">
        <!-- 学习计划模式 -->
        <template v-if="activeMode === 'plan'">
          <div class="panel-section">
            <h4><el-icon><List /></el-icon> 学习计划</h4>
            <p class="panel-desc">选择目标知识点，系统按前置依赖拓扑排序，生成从基础到目标的线性学习清单，每步附带推荐练习题</p>
            <el-select
              v-model="planTarget"
              filterable
              remote
              reserve-keyword
              placeholder="搜索目标知识点..."
              :remote-method="searchKnowledge"
              :loading="searchLoading"
              class="full-width"
              clearable
            >
              <el-option
                v-for="item in knowledgeOptions"
                :key="item.id"
                :label="item.name"
                :value="item.name"
              >
                <span>{{ item.name }}</span>
                <span class="option-type">{{ item.type }}</span>
              </el-option>
            </el-select>
            <div class="param-row">
              <span>追溯深度</span>
              <el-input-number v-model="planDepth" :min="1" :max="10" size="small" />
            </div>
            <div class="param-row">
              <span>每步推荐题数</span>
              <el-input-number v-model="planQuestionsPerStep" :min="0" :max="5" size="small" />
            </div>
            <div class="param-row">
              <span>训练强度</span>
              <el-radio-group v-model="planDifficultyPreference" size="small">
                <el-radio-button value="foundation">基础</el-radio-button>
                <el-radio-button value="balanced">均衡</el-radio-button>
                <el-radio-button value="challenge">挑战</el-radio-button>
              </el-radio-group>
            </div>
            <div class="depth-hint">
              当前学习档案已掌握 {{ masteredCount }} 个知识点
            </div>
            <el-button
              type="primary"
              :loading="planLoading"
              :disabled="!planTarget"
              class="full-width"
              @click="generatePlanList"
            >
              <el-icon><Search /></el-icon>
              生成学习计划
            </el-button>
          </div>

          <!-- 计划进度概览 -->
          <div v-if="planResult && planResult.steps.length" class="panel-section plan-progress-section">
            <h4><el-icon><TrendCharts /></el-icon> 学习进度</h4>
            <el-progress
              :percentage="planProgressPercent"
              :stroke-width="14"
              :format="() => `${planDoneSet.size}/${planTotalStepCount}`"
            />
            <div class="plan-progress-tips">
              勾选清单中的步骤记录进度；标记为「已掌握」的知识点在下次生成时将被跳过
            </div>
            <el-button
              v-if="planDoneSet.size"
              size="small"
              text
              type="danger"
              @click="resetPlanProgress"
            >清空本计划进度</el-button>
          </div>
        </template>

        <!-- 学习路径规划模式 -->
        <template v-if="activeMode === 'learning'">
          <div class="panel-section">
            <h4><el-icon><Aim /></el-icon> 学习路径规划</h4>
            <p class="panel-desc">选择一个目标知识点，系统自动追溯其所有前置依赖，生成从基础到目标的学习路径</p>
            <el-select
              v-model="learningTarget"
              filterable
              remote
              reserve-keyword
              placeholder="搜索目标知识点..."
              :remote-method="searchKnowledge"
              :loading="searchLoading"
              class="full-width"
              clearable
            >
              <el-option
                v-for="item in knowledgeOptions"
                :key="item.id"
                :label="item.name"
                :value="item.id"
              >
                <span>{{ item.name }}</span>
                <span class="option-type">{{ item.type }}</span>
              </el-option>
            </el-select>
            <div class="param-row">
              <span>最大追溯深度</span>
              <el-input-number v-model="learningDepth" :min="1" :max="8" size="small" />
            </div>
            <div class="depth-hint">
              <span v-if="learningDepth <= 2">仅查看直接和间接前置</span>
              <span v-else-if="learningDepth <= 4">覆盖多层依赖链</span>
              <span v-else>追踪完整知识脉络（最深8层）</span>
            </div>
            <el-button
              type="primary"
              :loading="learningLoading"
              :disabled="!learningTarget"
              class="full-width"
              @click="generateLearningPath"
            >
              <el-icon><Search /></el-icon>
              生成学习路径
            </el-button>
          </div>
        </template>

        <!-- 路径查找模式 -->
        <template v-if="activeMode === 'shortest'">
          <div class="panel-section">
            <h4><el-icon><Connection /></el-icon> 路径查找</h4>
            <p class="panel-desc">查找两个知识点之间的最短关系路径（包含所有边类型）</p>
            <div class="path-selector">
              <label>起始知识点</label>
              <el-select
                v-model="pathStart"
                filterable
                remote
                reserve-keyword
                placeholder="搜索起始知识点..."
                :remote-method="(q) => searchKnowledge(q, 'start')"
                :loading="startSearchLoading"
                class="full-width"
                clearable
              >
                <el-option
                  v-for="item in startOptions"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </div>
            <div class="path-arrow">
              <el-icon :size="20"><Bottom /></el-icon>
            </div>
            <div class="path-selector">
              <label>目标知识点</label>
              <el-select
                v-model="pathEnd"
                filterable
                remote
                reserve-keyword
                placeholder="搜索目标知识点..."
                :remote-method="(q) => searchKnowledge(q, 'end')"
                :loading="endSearchLoading"
                class="full-width"
                clearable
              >
                <el-option
                  v-for="item in endOptions"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </div>
            <div class="param-row">
              <span>搜索深度</span>
              <el-input-number v-model="shortestDepth" :min="1" :max="10" size="small" />
            </div>
            <div class="depth-hint">
              <span v-if="shortestDepth <= 3">快速查找，直连优先</span>
              <span v-else-if="shortestDepth <= 6">适中搜索范围</span>
              <span v-else>深度搜索，查找远距离关系</span>
            </div>
            <el-button
              type="primary"
              :loading="shortestLoading"
              :disabled="!pathStart || !pathEnd"
              class="full-width"
              @click="findPath"
            >
              <el-icon><Search /></el-icon>
              查找路径
            </el-button>
          </div>
        </template>

        <!-- 依赖分析模式 -->
        <template v-if="activeMode === 'dependency'">
          <div class="panel-section">
            <h4><el-icon><Share /></el-icon> 依赖分析</h4>
            <p class="panel-desc">分析知识点的前置依赖与后续依赖关系</p>
            <el-select
              v-model="depTarget"
              filterable
              remote
              reserve-keyword
              placeholder="搜索知识点..."
              :remote-method="searchKnowledge"
              :loading="searchLoading"
              class="full-width"
              clearable
            >
              <el-option
                v-for="item in knowledgeOptions"
                :key="item.id"
                :label="item.name"
                :value="item.id"
              >
                <span>{{ item.name }}</span>
                <span class="option-type">{{ item.type }}</span>
              </el-option>
            </el-select>
            <div class="param-row">
              <span>追溯深度</span>
              <el-input-number v-model="depDepth" :min="1" :max="8" size="small" />
            </div>
            <div class="depth-hint">
              <span v-if="depDepth <= 2">仅查看直接关联</span>
              <span v-else-if="depDepth <= 4">覆盖多层依赖关系</span>
              <span v-else>深度追溯，查看完整依赖链</span>
            </div>
            <el-button
              type="primary"
              :loading="depLoading"
              :disabled="!depTarget"
              class="full-width"
              @click="analyzeDependencies"
            >
              <el-icon><Search /></el-icon>
              分析依赖
            </el-button>
          </div>

          <!-- 依赖结果 -->
          <div v-if="depResult" class="panel-section dep-result">
            <div class="dep-block prereq">
              <h4>📥 前置依赖 ({{ depResult.prerequisites.length }})</h4>
              <div class="dep-list">
                <el-tag
                  v-for="item in depResult.prerequisites"
                  :key="item.name"
                  type="warning"
                  class="dep-tag"
                  @click="focusKnowledge(item.name)"
                >
                  {{ item.name }}
                </el-tag>
                <span v-if="!depResult.prerequisites.length" class="empty-tip">无前置依赖</span>
              </div>
            </div>
            <el-divider />
            <div class="dep-block next">
              <h4>📤 后续知识 ({{ depResult.next.length }})</h4>
              <div class="dep-list">
                <el-tag
                  v-for="item in depResult.next"
                  :key="item.name"
                  type="success"
                  class="dep-tag"
                  @click="focusKnowledge(item.name)"
                >
                  {{ item.name }}
                </el-tag>
                <span v-if="!depResult.next.length" class="empty-tip">无后续知识</span>
              </div>
            </div>
          </div>
        </template>

        <!-- 图例（按模式显示） -->
        <div v-if="showLegend" class="panel-section legend-section">
          <h4><el-icon><InfoFilled /></el-icon> 图例</h4>
          <!-- 学习路径模式 -->
          <template v-if="activeMode === 'learning'">
            <div class="legend-item"><span class="legend-dot target"></span> 目标知识点（距目标0层）</div>
            <div class="legend-item"><span class="legend-dot depth1"></span> 直接前置（距目标1层）</div>
            <div class="legend-item"><span class="legend-dot depth2"></span> 间接前置（距目标2层）</div>
            <div class="legend-item"><span class="legend-dot foundation"></span> 基础概念（距目标3+层）</div>
            <el-divider style="margin:8px 0" />
            <div class="legend-item legend-edge"><span class="legend-line solid"></span> 主要学习路径</div>
            <div class="legend-item legend-edge"><span class="legend-line dashed"></span> 分支学习路径</div>
          </template>
          <!-- 路径查找模式 -->
          <template v-if="activeMode === 'shortest'">
            <div class="legend-item"><span class="legend-dot start"></span> 起始知识点</div>
            <div class="legend-item"><span class="legend-dot target"></span> 目标知识点</div>
            <div class="legend-item"><span class="legend-dot middle"></span> 中间经过节点</div>
            <el-divider style="margin:8px 0" />
            <div class="legend-item legend-edge"><span class="legend-line legend-rel-prereq"></span> 先修关系 / 依赖</div>
            <div class="legend-item legend-edge"><span class="legend-line legend-rel-core"></span> 核心关联</div>
            <div class="legend-item legend-edge"><span class="legend-line legend-rel-other"></span> 其他关系类型</div>
          </template>
          <!-- 依赖分析模式 -->
          <template v-if="activeMode === 'dependency'">
            <div class="legend-item"><span class="legend-dot target"></span> 分析目标</div>
            <div class="legend-item"><span class="legend-dot prereq-dot"></span> 前置依赖（先修知识）</div>
            <div class="legend-item"><span class="legend-dot next-dot"></span> 后续知识（依赖本节点）</div>
            <el-divider style="margin:8px 0" />
            <div class="legend-item legend-edge"><span class="legend-arrow prereq-arr"></span> 先修关系</div>
            <div class="legend-item legend-edge"><span class="legend-arrow next-arr"></span> 后续依赖</div>
          </template>
        </div>
      </div>

      <!-- 右侧可视化区域 -->
      <div class="visual-area">
        <!-- 空状态 -->
        <div v-if="!hasResult" class="empty-state">
          <el-icon :size="80"><Guide /></el-icon>
          <h3>学习路径</h3>
          <p>选择一个知识点，探索从基础到进阶的学习路径</p>
          <div class="empty-tips">
            <el-tag type="info">学习路径规划</el-tag>
            <span>查看任意知识点的前置学习路径</span>
          </div>
          <div class="empty-tips">
            <el-tag type="info">路径查找</el-tag>
            <span>查找两个知识点之间的最短路径</span>
          </div>
          <div class="empty-tips">
            <el-tag type="info">依赖分析</el-tag>
            <span>分析知识点的依赖关系</span>
          </div>
        </div>

        <!-- 结果展示 -->
        <div v-else class="result-area">
          <!-- 学习计划模式结果 -->
          <template v-if="activeMode === 'plan'">
            <template v-if="planResult && planResult.steps.length">
              <div class="result-header">
                <div class="result-header-left">
                  <span>目标知识: <strong>{{ planResult.target.name }}</strong></span>
                  <el-tag size="small" effect="plain">状态 v{{ planResult.revision }}</el-tag>
                  <el-tag size="small" effect="plain">{{ planResult.total_steps }} 步</el-tag>
                  <el-tag v-if="planResult.mastered_skipped.length" size="small" type="success" effect="plain">
                    已跳过 {{ planResult.mastered_skipped.length }} 个已掌握
                  </el-tag>
                  <el-tag v-if="planResult.completed_skipped?.length" size="small" type="info" effect="plain">
                    已跳过 {{ planResult.completed_skipped.length }} 个已完成
                  </el-tag>
                </div>
                <div class="result-header-actions">
                  <span class="result-header-right">完成 {{ planDoneSet.size }}/{{ planTotalStepCount }}</span>
                  <el-button size="small" type="warning" plain @click="highlightPlanInGraph">图谱高亮</el-button>
                </div>
              </div>
              <el-alert
                v-if="planResult.review_before_plan?.length"
                type="warning"
                :closable="false"
                :title="`路径开始前有 ${planResult.review_before_plan.length} 道待复习题`"
                show-icon
              />
              <div class="plan-list">
                <div
                  v-for="step in planResult.steps"
                  :key="step.id"
                  class="plan-step"
                  :class="{ 'plan-step-done': planDoneSet.has(step.id), 'plan-step-target': step.is_target }"
                >
                  <div class="plan-step-main">
                    <el-checkbox
                      :model-value="planDoneSet.has(step.id)"
                      @change="toggleStepDone(step)"
                      size="large"
                    />
                    <span class="plan-step-order">{{ step.order }}</span>
                    <div class="plan-step-body">
                      <div class="plan-step-title">
                        <span class="plan-step-name" @click="viewInKnowledge({ name: step.name })">{{ step.name }}</span>
                        <el-tag v-if="step.is_target" size="small" type="danger" effect="dark">目标</el-tag>
                        <el-tag v-else size="small" type="info" effect="plain">距目标 {{ step.depth }} 层</el-tag>
                      </div>
                      <div v-if="step.prerequisites.length" class="plan-step-prereq">
                        前置：
                        <span v-for="(p, pi) in step.prerequisites" :key="p.id">
                          {{ p.name }}<span v-if="pi < step.prerequisites.length - 1">、</span>
                        </span>
                      </div>
                      <div class="plan-step-prereq">
                        {{ masteryStateLabel(step.mastery_state) }}
                        <span v-if="step.mistake_count"> · {{ step.mistake_count }} 道待复习</span>
                        <el-button
                          v-if="step.mistake_count"
                          link
                          type="warning"
                          size="small"
                          @click="router.push({ path: '/mistakes', query: { knowledge_id: step.id } })"
                        >查看错题</el-button>
                      </div>
                      <!-- 配套练习题 -->
                      <div v-if="step.questions && step.questions.length" class="plan-questions">
                        <div
                          v-for="q in step.questions"
                          :key="q.id"
                          class="plan-question"
                        >
                          <el-tag
                            size="small"
                            :type="difficultyTagType(q.difficulty)"
                            effect="light"
                            class="q-difficulty"
                          >{{ q.difficulty }}</el-tag>
                          <a
                            v-if="q.url"
                            :href="q.url"
                            target="_blank"
                            rel="noopener"
                            class="q-name"
                          >{{ q.name }}</a>
                          <span v-else class="q-name">{{ q.name }}</span>
                          <span v-if="q.pass_rate" class="q-pass">通过率 {{ q.pass_rate }}%</span>
                          <el-button-group class="q-attempt-actions">
                            <el-tooltip content="记录做错">
                              <el-button size="small" type="danger" plain @click="recordPlanQuestion(step, q, false)">
                                <el-icon><CircleClose /></el-icon>
                              </el-button>
                            </el-tooltip>
                            <el-tooltip content="记录做对">
                              <el-button size="small" type="success" plain @click="recordPlanQuestion(step, q, true)">
                                <el-icon><CircleCheck /></el-icon>
                              </el-button>
                            </el-tooltip>
                          </el-button-group>
                        </div>
                      </div>
                    </div>
                    <el-button
                      size="small"
                      :type="masteredSet.has(step.id) ? 'success' : ''"
                      :plain="!masteredSet.has(step.id)"
                      class="plan-mastered-btn"
                      @click="toggleStepMastered(step)"
                    >
                      {{ masteredSet.has(step.id) ? '✓ 已掌握' : '标记已掌握' }}
                    </el-button>
                  </div>
                </div>
              </div>
            </template>
            <template v-else-if="planResult && (planResult.already_mastered || planResult.already_completed)">
              <div class="no-result">
                <el-icon :size="48" color="#67c23a"><SuccessFilled /></el-icon>
                <p v-if="planResult.already_mastered && planResult.target_manual_override === 'mastered'">
                  目标知识点已自报掌握，无需学习计划。<br/>可取消自报标记后重新生成。
                </p>
                <p v-else-if="planResult.already_mastered">
                  目标知识点已有测评掌握证据，无需学习计划。
                </p>
                <p v-else>目标知识点已在当前计划中完成。<br/>可清空该计划进度后重新生成。</p>
                <el-button
                  v-if="planResult.already_mastered && planResult.target_manual_override === 'mastered'"
                  size="small"
                  @click="unmarkTarget"
                >取消自报掌握并重新生成</el-button>
                <el-button
                  v-else-if="planResult.already_completed"
                  size="small"
                  @click="resumeCompletedTarget"
                >清空进度并重新生成</el-button>
              </div>
            </template>
            <div v-else class="no-result">
              <el-icon :size="48"><WarningFilled /></el-icon>
              <p>{{ planNoResultMsg }}</p>
            </div>
          </template>

          <!-- 学习路径模式结果 -->
          <template v-if="activeMode === 'learning'">
            <template v-if="learningPaths.length">
              <div class="result-header">
                <div class="result-header-left">
                  <span>目标知识: <strong>{{ learningTargetName }}</strong></span>
                  <el-tag size="small" effect="plain">{{ learningPaths.length }} 条路径</el-tag>
                  <el-tag size="small" type="warning" effect="plain">最深追溯 {{ maxPathDepth }} 层</el-tag>
                </div>
                <div class="result-header-actions">
                  <span class="result-header-right">共 {{ learningNodeCount }} 个关联知识点</span>
                  <el-button size="small" type="warning" plain @click="highlightLearningInGraph">图谱高亮</el-button>
                </div>
              </div>
              <div ref="learningGraphRef" class="graph-container"></div>
            </template>
            <div v-else class="no-result">
              <el-icon :size="48"><WarningFilled /></el-icon>
              <p>{{ learningNoResultMsg }}</p>
            </div>
          </template>

          <!-- 路径查找模式结果 -->
          <template v-if="activeMode === 'shortest'">
            <template v-if="shortestResult && shortestResult.nodes && shortestResult.nodes.length">
              <div class="result-header">
                <div class="result-header-left">
                  <span><strong>{{ shortestStartName }}</strong> → <strong>{{ shortestEndName }}</strong></span>
                  <el-tag size="small" type="success" effect="plain">最短路径</el-tag>
                </div>
                <div class="result-header-actions">
                  <span class="result-header-right">{{ shortestResult.length }} 步 · {{ shortestResult.nodes.length }} 个节点</span>
                  <el-button size="small" type="warning" plain @click="highlightShortestInGraph">图谱高亮</el-button>
                </div>
              </div>
              <div class="shortest-layout">
                <div ref="shortestGraphRef" class="graph-container" style="flex: 1;"></div>
                <!-- 路径详情面板 -->
                <div v-if="shortestPathSteps.length" class="path-steps-panel">
                  <h4>📋 路径详情</h4>
                  <div class="path-step" v-for="(step, si) in shortestPathSteps" :key="si">
                    <div class="step-node" :class="{ 'step-start': si === 0, 'step-end': si === shortestPathSteps.length - 1 }">
                      <span class="step-dot"></span>
                      <span class="step-name">{{ step.node }}</span>
                      <el-tag size="small" type="info">{{ step.type }}</el-tag>
                    </div>
                    <div v-if="si < shortestPathSteps.length - 1" class="step-rel">
                      <span class="step-arrow">│</span>
                      <el-tag size="small" :type="step.isPrereq ? 'warning' : ''" effect="plain">
                        {{ step.relLabel }}
                        <span v-if="step.reverse">(反向)</span>
                      </el-tag>
                      <span class="step-arrow">↓</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>
            <div v-else class="no-result">
              <el-icon :size="48"><WarningFilled /></el-icon>
              <p>{{ shortestNoResultMsg }}</p>
            </div>
          </template>

          <!-- 依赖分析（已在左侧面板展示，这里显示图） -->
          <template v-if="activeMode === 'dependency'">
            <template v-if="depResult && ((depResult.prerequisites && depResult.prerequisites.length) || (depResult.next && depResult.next.length))">
              <div class="result-header">
                <div class="result-header-left">
                  <span>分析目标: <strong>{{ depTargetName }}</strong></span>
                  <el-tag size="small" type="warning" effect="plain">前置 {{ depResult.prerequisites?.length || 0 }}</el-tag>
                  <el-tag size="small" type="success" effect="plain">后续 {{ depResult.next?.length || 0 }}</el-tag>
                </div>
                <el-button size="small" type="warning" plain @click="highlightDependenciesInGraph">图谱高亮</el-button>
              </div>
              <div ref="depGraphRef" class="graph-container"></div>
            </template>
            <div v-else class="no-result">
              <el-icon :size="48"><WarningFilled /></el-icon>
              <p>该知识点暂无依赖关系数据</p>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- 节点详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="detailNode?.name || '节点详情'" width="600px">
      <template v-if="detailNode">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="类型">
            <el-tag size="small">{{ detailNode.typeLabel || detailNode.type || '未知' }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="detailNode.chapter" label="章节">{{ detailNode.chapter }}</el-descriptions-item>
          <el-descriptions-item label="名称" :span="2">{{ detailNode.name }}</el-descriptions-item>
          <el-descriptions-item v-if="detailNode.difficulty" label="难度">{{ detailNode.difficulty }}</el-descriptions-item>
          <el-descriptions-item v-if="detailNode.description" label="描述" :span="2">{{ detailNode.description }}</el-descriptions-item>
        </el-descriptions>
        <div style="margin-top: 16px; text-align: right;">
          <el-button type="primary" size="small" @click="viewInGraph(detailNode)">
            在图谱中查看
          </el-button>
          <el-button size="small" @click="viewInKnowledge(detailNode)">
            查看详情
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onUnmounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Guide, Aim, Connection, Search, Share, Bottom, WarningFilled, InfoFilled,
  List, TrendCharts, SuccessFilled, CircleCheck, CircleClose
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { DataSet, Network } from 'vis-network/standalone'
import { findShortestPath, getLearningPath, getDependencies } from '@/api/path'
import { getKnowledgePoints } from '@/api/graph'
import { generateLearnerPlan, learnerErrorMessage } from '@/api/learner'
import {
  getMastered, setMastered, unsetMastered,
  getPlanDone, togglePlanStep, clearPlanDone,
  getRevision, loadLearningState, recordQuestionAttempt
} from '@/stores/progress'

const router = useRouter()
const route = useRoute()
const PATH_WORKSPACE_KEY = 'kg_path_workspace_v1'
let restoringWorkspace = false

// ============ 模式切换 ============
const activeMode = ref('plan')
const showLegend = ref(false)

// ============ 模式0: 学习计划 ============
const planTarget = ref('')
const planDepth = ref(6)
const planQuestionsPerStep = ref(3)
const planDifficultyPreference = ref('balanced')
const planLoading = ref(false)
const planResult = ref(null)
const planNoResultMsg = ref('')
const masteredSet = ref(new Set(getMastered()))
const planDoneSet = ref(new Set())

const masteredCount = computed(() => masteredSet.value.size)
const planTotalStepCount = computed(() => (
  (planResult.value?.total_steps || 0) + (planResult.value?.completed_skipped?.length || 0)
))
const planProgressPercent = computed(() => {
  if (!planTotalStepCount.value) return 0
  return Math.round((planDoneSet.value.size / planTotalStepCount.value) * 100)
})

function difficultyTagType(d) {
  return { '简单': 'success', '中等': 'warning', '困难': 'danger', '星耀': 'danger' }[d] || 'info'
}

async function generatePlanList() {
  if (!planTarget.value) return
  planLoading.value = true
  try {
    const res = await generateLearnerPlan({
      target: planTarget.value,
      max_depth: planDepth.value,
      difficulty_preference: planDifficultyPreference.value,
      questions_per_step: planQuestionsPerStep.value,
      expected_revision: getRevision()
    })
    if (res?.target) {
      planResult.value = res
      hasResult.value = true
      if (!res.steps.length && !res.already_mastered && !res.already_completed) {
        planNoResultMsg.value = `"${planTarget.value}" 未找到前置依赖，可能已是基础知识点`
      } else {
        planNoResultMsg.value = ''
        planDoneSet.value = new Set(getPlanDone(res.target.id))
        ;(res.completed_skipped || []).forEach(item => planDoneSet.value.add(item.id))
      }
    } else {
      planResult.value = null
      planNoResultMsg.value = '生成学习计划失败'
      hasResult.value = true
    }
  } catch (e) {
    ElMessage.error(learnerErrorMessage(e, '生成学习计划失败'))
    console.error(e)
  } finally {
    planLoading.value = false
  }
}

async function toggleStepDone(step) {
  if (!planResult.value) return
  try {
    const done = await togglePlanStep(planResult.value.target.id, step.id)
    planDoneSet.value = new Set(done)
    if (planDoneSet.value.size === planTotalStepCount.value) {
      ElMessage.success('本计划已全部完成')
    }
  } catch (error) {
    ElMessage.error(learnerErrorMessage(error, '更新步骤失败，请刷新后重试'))
  }
}

async function toggleStepMastered(step) {
  try {
    if (masteredSet.value.has(step.id)) {
      await unsetMastered(step.id, step.name)
    } else {
      await setMastered(step.id, step.name)
      ElMessage.success(`已标记「${step.name}」为已掌握`)
    }
    masteredSet.value = new Set(getMastered())
  } catch (error) {
    ElMessage.error(learnerErrorMessage(error, '更新掌握状态失败，请刷新后重试'))
  }
}

async function resetPlanProgress() {
  if (!planResult.value) return
  try {
    await clearPlanDone(planResult.value.target.id)
    planDoneSet.value = new Set()
  } catch (error) {
    ElMessage.error(learnerErrorMessage(error, '清空进度失败，请刷新后重试'))
  }
}

async function unmarkTarget() {
  if (!planResult.value?.target?.id) return
  try {
    await unsetMastered(planResult.value.target.id, planResult.value.target.name)
    masteredSet.value = new Set(getMastered())
    await generatePlanList()
  } catch (error) {
    ElMessage.error(learnerErrorMessage(error, '取消自报掌握失败，请刷新后重试'))
  }
}

async function resumeCompletedTarget() {
  if (!planResult.value?.target?.id) return
  await clearPlanDone(planResult.value.target.id)
  planDoneSet.value = new Set()
  await generatePlanList()
}

function masteryStateLabel(state) {
  return {
    assessed_mastery: '测评已掌握',
    self_reported_mastery: '自报已掌握',
    soft_confidence: '较可能掌握',
    weak: '薄弱',
    untested: '未测试'
  }[state] || '未测试'
}

async function recordPlanQuestion(step, question, correct) {
  try {
    await recordQuestionAttempt(question.id, {
      correct,
      targetId: planResult.value.target.id,
      pathNodeId: step.id
    })
    ElMessage({
      type: correct ? 'success' : 'warning',
      message: correct ? '已记录为做对' : '已加入错题本'
    })
    await generatePlanList()
  } catch (error) {
    ElMessage.error(learnerErrorMessage(error, '记录作答失败，请刷新后重试'))
  }
}


// ============ 知识点搜索（共用） ============
const searchLoading = ref(false)
const knowledgeOptions = ref([])
const startOptions = ref([])
const endOptions = ref([])
const startSearchLoading = ref(false)
const endSearchLoading = ref(false)
const allKnowledgePoints = ref([])

// 初始化加载所有知识点
async function loadAllKnowledge() {
  try {
    const res = await getKnowledgePoints(2000)
    if (res.success && res.data) {
      allKnowledgePoints.value = res.data
    }
  } catch (e) {
    console.error('加载知识点失败:', e)
  }
}

// 共用搜索
function searchKnowledge(query, target) {
  if (!query) {
    const empty = []
    if (target === 'start') startOptions.value = empty
    else if (target === 'end') endOptions.value = empty
    else knowledgeOptions.value = empty
    return
  }
  if (target === 'start') startSearchLoading.value = true
  else if (target === 'end') endSearchLoading.value = true
  else searchLoading.value = true

  const q = query.toLowerCase()
  const filtered = allKnowledgePoints.value
    .filter(kp => kp.name && kp.name.toLowerCase().includes(q))
    .slice(0, 20)
    .map(kp => ({
      id: kp.id || kp.node_id,
      name: kp.name,
      type: kp.type || kp.node_type || 'KnowledgeNode'
    }))

  if (target === 'start') { startOptions.value = filtered; startSearchLoading.value = false }
  else if (target === 'end') { endOptions.value = filtered; endSearchLoading.value = false }
  else { knowledgeOptions.value = filtered; searchLoading.value = false }
}

// ============ 模式1: 学习路径规划 ============
const learningTarget = ref('')
const learningTargetName = ref('')
const learningDepth = ref(4)
const learningLoading = ref(false)
const learningPaths = ref([])
const learningNoResultMsg = ref('')
const hasResult = ref(false)
const learningGraphRef = ref(null)
const maxPathDepth = ref(0)
const learningNodeCount = ref(0)

async function generateLearningPath() {
  if (!learningTarget.value) return
  learningLoading.value = true

  try {
    const targetKp = knowledgeOptions.value.find(k => k.id === learningTarget.value)
    learningTargetName.value = targetKp?.name || learningTarget.value

    const res = await getLearningPath(learningTargetName.value, learningDepth.value)
    if (res.success && res.data && Array.isArray(res.data) && res.data.length > 0) {
      learningPaths.value = res.data
      learningNoResultMsg.value = ''
      hasResult.value = true
      showLegend.value = true
      // 计算统计信息
      maxPathDepth.value = Math.max(...res.data.map(p => p.length || 0))
      const allNames = new Set()
      res.data.forEach(p => (p.nodes || []).forEach(n => allNames.add(n.name)))
      learningNodeCount.value = allNames.size
      await nextTick()
      renderLearningPath()
    } else {
      learningPaths.value = []
      learningNoResultMsg.value = `"${learningTargetName.value}" 在当前追溯深度内未找到先修关系。可尝试增大深度，或该知识点已为基础概念`
      hasResult.value = true
      showLegend.value = false
      ElMessage.info(res.message || '未找到学习路径')
    }
  } catch (e) {
    ElMessage.error('获取学习路径失败')
    console.error(e)
  } finally {
    learningLoading.value = false
  }
}

// ============ 模式2: 路径查找 ============
const pathStart = ref('')
const pathEnd = ref('')
const shortestDepth = ref(5)
const shortestLoading = ref(false)
const shortestResult = ref(null)
const shortestNoResultMsg = ref('')
const shortestStartName = ref('')
const shortestEndName = ref('')
const shortestPathSteps = ref([])
const shortestGraphRef = ref(null)

async function findPath() {
  if (!pathStart.value || !pathEnd.value) return

  // 校验：不能选择相同知识点
  if (pathStart.value === pathEnd.value) {
    ElMessage.warning('起始知识点和目标知识点不能相同')
    return
  }

  shortestLoading.value = true

  try {
    // 优先从搜索选项中查找名称，回退到全量知识点列表
    const startKp = startOptions.value.find(k => k.id === pathStart.value)
      || allKnowledgePoints.value.find(k => (k.id || k.node_id) === pathStart.value)
    const endKp = endOptions.value.find(k => k.id === pathEnd.value)
      || allKnowledgePoints.value.find(k => (k.id || k.node_id) === pathEnd.value)
    shortestStartName.value = startKp?.name || pathStart.value
    shortestEndName.value = endKp?.name || pathEnd.value

    // 按名称查询而不是数据库节点ID：重建数据库后ID会全部变化，名称保持稳定
    const res = await findShortestPath({
      start: shortestStartName.value,
      end: shortestEndName.value,
      max_depth: shortestDepth.value
    })
    if (res.success && res.data && res.data.nodes && res.data.nodes.length > 0) {
      shortestResult.value = res.data
      shortestNoResultMsg.value = ''
      hasResult.value = true
      showLegend.value = true
      await nextTick()
      renderShortestPath()
    } else {
      shortestResult.value = null
      shortestNoResultMsg.value = '未找到两个知识点之间的路径，请尝试增加搜索深度或更换知识点'
      hasResult.value = true
      showLegend.value = false
      ElMessage.info(res.message || '未找到路径')
    }
  } catch (e) {
    ElMessage.error('路径查找失败')
    console.error(e)
  } finally {
    shortestLoading.value = false
  }
}

// ============ 模式3: 依赖分析 ============
const depTarget = ref('')
const depTargetName = ref('')
const depDepth = ref(4)
const depLoading = ref(false)
const depResult = ref(null)
const depGraphRef = ref(null)

async function analyzeDependencies() {
  if (!depTarget.value) return
  depLoading.value = true

  try {
    const targetKp = knowledgeOptions.value.find(k => k.id === depTarget.value)
    const name = targetKp?.name || depTarget.value
    depTargetName.value = name

    const res = await getDependencies(name, depDepth.value)
    if (res.success && res.data) {
      depResult.value = res.data
      hasResult.value = true
      showLegend.value = true
      await nextTick()
      renderDependencyGraph(name)
    } else {
      depResult.value = null
      hasResult.value = true
      showLegend.value = false
      ElMessage.info(res.message || '未找到依赖关系')
    }
  } catch (e) {
    ElMessage.error('依赖分析失败')
    console.error(e)
  } finally {
    depLoading.value = false
  }
}

// ============ 可视化渲染 ============
let learningNetwork = null
let shortestNetwork = null
let depNetwork = null

// 节点类型 → 中文映射
function getTypeLabel(type) {
  const map = {
    'KnowledgeNode': '知识点',
    'KnowledgePoint': '知识点',
    'Chapter': '章节',
    'Question': '题目',
    'NodeType': '节点类型'
  }
  return map[type] || type || '未知'
}

// 关系类型 → 中文映射
const relLabelMap = {
  'PREREQUISITE': '先修',
  'REQUIRES': '先修依赖',
  'HAS_CORE_RELATION': '核心关联',
  'PARENT_OF': '父子',
  'BELONGS_TO': '属于',
  'HAS_INSTANCE': '实例'
}

const relColorMap = {
  'PREREQUISITE': '#e6a23c',
  'REQUIRES': '#e6a23c',
  'HAS_CORE_RELATION': '#409eff',
  'PARENT_OF': '#67c23a',
  'BELONGS_TO': '#9c27b0',
  'HAS_INSTANCE': '#00bcd4'
}

// 先修类关系类型（用于标签颜色判断）
const isPrerequisiteRel = (type) => type === 'PREREQUISITE' || type === 'REQUIRES'

function getRelLabel(type) {
  return relLabelMap[type] || type || '关联'
}

function getRelColor(type) {
  return relColorMap[type] || '#909399'
}

// ============ 安全的 Tooltip 构建（纯文本 + 换行） ============
function makeTooltip(lines) {
  // lines: [标题字符串] 或 [标签, 值]
  return lines.map(r => {
    if (Array.isArray(r)) {
      if (r.length >= 2) {
        return `${r[0]}：${r[1]}`
      }
      return r[0]
    }
    return r
  }).join('\n')
}

// 按深度级别着色（用于学习路径）
// depth = 距目标的层级；API 返回已 reverse：nodes[0]=最基础 → nodes[last]=目标
function getDepthColor(depth) {
  // depth=0: 目标节点（不在此处理，外部 isTarget 判断）
  // depth=1: 直接前置 → 橙色
  // depth=2: 间接前置 → 蓝色
  // depth>=3: 基础概念 → 绿色系
  if (depth === 1) return '#e6a23c'   // 橙色 — 直接前置
  if (depth === 2) return '#409eff'   // 蓝色 — 间接前置
  if (depth >= 3) return '#67c23a'    // 绿色 — 基础概念（最深）
  return '#909399'
}

function renderLearningPath() {
  if (!learningGraphRef.value) return
  if (learningNetwork) learningNetwork.destroy()

  // ===== 第一遍：收集所有节点，计算距目标的最小深度 =====
  const nodeDataMap = new Map()  // key → node原始数据
  const nodeDepthMap = new Map() // key → 最小深度（离目标最近的距离）

  learningPaths.value.forEach(path => {
    const pathNodes = path.nodes || []
    pathNodes.forEach((node, idx) => {
      const key = node.id || node.name
      const depth = pathNodes.length - 1 - idx  // 距目标的层级
      nodeDataMap.set(key, node)
      const prevDepth = nodeDepthMap.get(key)
      if (prevDepth === undefined || depth < prevDepth) {
        nodeDepthMap.set(key, depth)
      }
    })
  })

  // ===== 第二遍：按深度从大到小创建节点（最深基地先创建，目标最后） =====
  const sortedKeys = [...nodeDepthMap.keys()].sort(
    (a, b) => (nodeDepthMap.get(b) || 0) - (nodeDepthMap.get(a) || 0)
  )

  const nodes = []
  const nodeMap = new Map()  // key → vis nodeId
  let nodeId = 0

  sortedKeys.forEach(key => {
    const depth = nodeDepthMap.get(key) || 0
    const node = nodeDataMap.get(key)
    const isTarget = depth === 0
    const bgColor = isTarget ? '#f56c6c' : getDepthColor(depth)
    const depthLabel = isTarget ? '目标节点' : `距目标 ${depth} 层`

    nodeMap.set(key, nodeId)
    const typeLabel = getTypeLabel(node.type)
    nodes.push({
      id: nodeId,
      label: node.name || node.id,
      title: makeTooltip([
        [node.name || node.id],
        ['类型', typeLabel],
        [depthLabel]
      ]),
      color: { background: bgColor, border: isTarget ? '#c0392b' : '#ffffff' },
      font: { color: isTarget ? '#ffffff' : '#303133', size: isTarget ? 14 : 12, bold: isTarget ? { size: 14 } : undefined },
      shape: 'box',
      borderWidth: isTarget ? 3 : 1,
      nodeData: { ...node, typeLabel },
      level: depth
    })
    nodeId++
  })

  // ===== 第三遍：创建边 =====
  const edges = []
  const edgeSet = new Set()  // 去重 "from→to"

  learningPaths.value.forEach((path, pathIdx) => {
    const pathNodes = path.nodes || []
    const pathRels = path.relationships || []

    pathRels.forEach((rel, idx) => {
      const fromNode = pathNodes[idx]
      const toNode = pathNodes[idx + 1]
      if (!fromNode || !toNode) return
      const fromKey = fromNode.id || fromNode.name
      const toKey = toNode.id || toNode.name
      const fromId = nodeMap.get(fromKey)
      const toId = nodeMap.get(toKey)
      if (fromId === undefined || toId === undefined) return

      const edgeKey = `${fromId}→${toId}`
      if (edgeSet.has(edgeKey)) return  // 同一条边只画一次（取第一条路径的样式）
      edgeSet.add(edgeKey)

      const edgeLabel = getRelLabel(rel.type)
      edges.push({
        from: fromId,
        to: toId,
        label: edgeLabel,
        arrows: 'to',
        color: { color: pathIdx === 0 ? '#409eff' : '#c0c4cc' },
        width: pathIdx === 0 ? 2 : 1,
        dashes: pathIdx > 0
      })
    })
  })

  if (nodes.length === 0) return

  learningNetwork = createNetwork(learningGraphRef.value, nodes, edges, 'LR')
}

function renderShortestPath() {
  if (!shortestGraphRef.value || !shortestResult.value) return
  if (shortestNetwork) shortestNetwork.destroy()

  const nodes = []
  const edges = []
  const pathNodes = shortestResult.value.nodes || []
  const pathRels = shortestResult.value.relationships || []

  // 构建 node id → nodeIdx 映射
  const nodeIdToIdx = {}
  pathNodes.forEach((node, idx) => {
    nodeIdToIdx[node.id || node.name] = idx
    const isStart = idx === 0
    const isEnd = idx === pathNodes.length - 1

    let color = '#e6a23c' // 中间节点默认
    if (isStart) color = '#67c23a'
    else if (isEnd) color = '#f56c6c'

    const roleLabel = isStart ? '【起始】' : isEnd ? '【目标】' : `【第${idx}步】`
    const nodeName = node.name || node.id || '未知'
    const typeLabel = getTypeLabel(node.type)
    nodes.push({
      id: idx,
      label: nodeName.length > 15 ? nodeName.slice(0, 14) + '…' : nodeName,
      title: makeTooltip([
        [`${roleLabel} ${nodeName}`],
        ['类型', typeLabel]
      ]),
      color: { background: color, border: isStart || isEnd ? '#ffffff' : '#ffffff' },
      font: { color: isStart || isEnd ? '#ffffff' : '#303133', size: isStart || isEnd ? 14 : 12, bold: isStart || isEnd ? { size: 14 } : undefined },
      shape: 'box',
      borderWidth: isStart || isEnd ? 3 : 1,
      nodeData: {
        id: node.id,
        name: nodeName,
        type: node.type || 'KnowledgeNode',
        typeLabel,
        ...(node.properties || {})
      }
    })
  })

  // 创建边 —— 根据关系的 from/to 确定实际方向
  pathRels.forEach(rel => {
    const fromIdx = nodeIdToIdx[rel.from]
    const toIdx = nodeIdToIdx[rel.to]
    if (fromIdx === undefined || toIdx === undefined) return

    const relType = rel.type || '关联'
    const edgeLabel = getRelLabel(relType)
    const edgeColor = getRelColor(relType)

    // 判断关系方向是否与路径方向一致
    // 路径方向：start → ... → end（索引递增）
    // 如果 rel.from 的索引 < rel.to 的索引，方向一致，箭头指向 to
    // 否则箭头方向相反
    const isForward = fromIdx < toIdx

    edges.push({
      from: isForward ? fromIdx : toIdx,
      to: isForward ? toIdx : fromIdx,
      label: edgeLabel,
      arrows: isForward ? 'to' : 'to', // vis-network 总是箭头的 from→to 方向
      color: { color: edgeColor },
      width: 2,
      font: { size: 10, color: edgeColor, strokeWidth: 2, strokeColor: '#ffffff' }
    })
  })

  // 构建路径步骤详情
  const steps = pathNodes.map((node, idx) => {
    const nodeName = node.name || node.id || '未知'
    const step = {
      node: nodeName,
      type: getTypeLabel(node.type)
    }
    if (idx < pathRels.length) {
      const rel = pathRels[idx]
      const fromIdx = nodeIdToIdx[rel.from]
      const toIdx = nodeIdToIdx[rel.to]
      step.relType = rel.type || '关联'
      step.relLabel = getRelLabel(rel.type)
      step.reverse = (fromIdx !== undefined && toIdx !== undefined && fromIdx > toIdx)
      step.isPrereq = isPrerequisiteRel(rel.type)
    }
    return step
  })
  shortestPathSteps.value = steps

  shortestNetwork = createNetwork(shortestGraphRef.value, nodes, edges, 'LR')
}

function renderDependencyGraph(targetName) {
  if (!depGraphRef.value || !depResult.value) return
  if (depNetwork) depNetwork.destroy()

  const nodes = []
  const edges = []
  let nodeId = 0

  // 目标节点（居中）
  nodes.push({
    id: nodeId,
    label: targetName,
    title: makeTooltip([['🎯 分析目标', targetName]]),
    color: { background: '#f56c6c', border: '#c0392b' },
    font: { color: '#ffffff', size: 15, bold: { size: 15 } },
    shape: 'box',
    borderWidth: 3
  })
  const targetId = nodeId
  nodeId++

  // 前置依赖（上方，箭头指向目标）
  ;(depResult.value.prerequisites || []).forEach(item => {
    nodes.push({
      id: nodeId,
      label: item.name,
      title: makeTooltip([
        ['前置依赖', item.name],
        ['类型', getTypeLabel(item.type)]
      ]),
      color: { background: '#e6a23c', border: '#f0c78e' },
      font: { color: '#303133', size: 13 },
      shape: 'box',
      borderWidth: 1,
      nodeData: item
    })
    edges.push({
      from: nodeId,
      to: targetId,
      arrows: 'to',
      color: { color: '#e6a23c' },
      label: '先修',
      width: 2
    })
    nodeId++
  })

  // 后续知识（下方，箭头从目标出发）
  ;(depResult.value.next || []).forEach(item => {
    nodes.push({
      id: nodeId,
      label: item.name,
      title: makeTooltip([
        ['后续知识', item.name],
        ['类型', getTypeLabel(item.type)]
      ]),
      color: { background: '#67c23a', border: '#b6e0a0' },
      font: { color: '#303133', size: 13 },
      shape: 'box',
      borderWidth: 1,
      nodeData: item
    })
    edges.push({
      from: targetId,
      to: nodeId,
      arrows: 'to',
      color: { color: '#67c23a' },
      label: '先修',
      width: 2
    })
    nodeId++
  })

  if (nodes.length <= 1) return

  depNetwork = createNetwork(depGraphRef.value, nodes, edges, 'UD')
}

function createNetwork(container, nodes, edges, direction) {
  if (!container) return null

  const data = { nodes: new DataSet(nodes), edges: new DataSet(edges) }
  const options = {
    layout: {
      hierarchical: {
        enabled: true,
        direction: direction,
        sortMethod: 'directed',
        levelSeparation: direction === 'LR' ? 200 : 150,
        nodeSpacing: 180
      }
    },
    physics: { enabled: false },
    interaction: { hover: true, zoomView: true },
    edges: {
      smooth: { type: 'cubicBezier', forceDirection: 'horizontal' },
      font: { size: 11, color: '#606266', strokeWidth: 2, strokeColor: '#ffffff' }
    }
  }

  const network = new Network(container, data, options)

  network.on('click', (params) => {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0]
      const node = nodes.find(n => n.id === nodeId)
      if (node?.nodeData) {
        detailNode.value = node.nodeData
        detailVisible.value = true
      }
    }
  })

  return network
}

// ============ 节点详情 ============
const detailVisible = ref(false)
const detailNode = ref(null)

function viewInGraph(node) {
  persistPathWorkspace()
  router.push({ path: '/graph', query: { focus: node.id || node.name } })
}

function navigateToGraphHighlight(nodeIds, focusId) {
  const ids = [...new Set(nodeIds.map(value => String(value || '').trim()).filter(Boolean))].slice(0, 200)
  if (!ids.length) {
    ElMessage.warning('当前结果没有可用于图谱定位的业务 ID')
    return
  }
  persistPathWorkspace()
  router.push({
    path: '/graph',
    query: {
      focus: focusId || ids[ids.length - 1],
      highlight: ids.join(',')
    }
  })
}

function highlightPlanInGraph() {
  navigateToGraphHighlight(
    planResult.value?.steps?.map(step => step.id) || [],
    planResult.value?.target?.id
  )
}

function highlightLearningInGraph() {
  const ids = learningPaths.value.flatMap(path => (path.nodes || []).map(node => node.id))
  navigateToGraphHighlight(ids, learningTarget.value)
}

function highlightShortestInGraph() {
  navigateToGraphHighlight(
    shortestResult.value?.nodes?.map(node => node.id) || [],
    shortestResult.value?.nodes?.[0]?.id
  )
}

function highlightDependenciesInGraph() {
  navigateToGraphHighlight([
    depResult.value?.target?.id,
    ...(depResult.value?.prerequisites || []).map(node => node.id),
    ...(depResult.value?.next || []).map(node => node.id)
  ], depResult.value?.target?.id)
}

function viewInKnowledge(node) {
  persistPathWorkspace()
  router.push({ path: '/knowledge', query: { focus: node.id || node.name } })
}

function focusKnowledge(name) {
  depTarget.value = null
  const found = allKnowledgePoints.value.find(k => k.name === name)
  if (found) {
    depTarget.value = found.id || found.node_id
    nextTick(() => analyzeDependencies())
  }
}

// ============ 页面工作区持久化 ============
function readPathWorkspace() {
  try {
    const raw = sessionStorage.getItem(PATH_WORKSPACE_KEY)
    const value = raw ? JSON.parse(raw) : null
    return value && value.version === 1 ? value : null
  } catch (error) {
    console.warn('[path] 读取页面工作区失败:', error)
    return null
  }
}

function persistPathWorkspace() {
  if (restoringWorkspace) return
  const workspace = {
    version: 1,
    active_mode: activeMode.value,
    plan: {
      target: planTarget.value,
      depth: planDepth.value,
      questions_per_step: planQuestionsPerStep.value,
      difficulty_preference: planDifficultyPreference.value,
      result: planResult.value,
      no_result_message: planNoResultMsg.value
    },
    learning: {
      target: learningTarget.value,
      target_name: learningTargetName.value,
      depth: learningDepth.value,
      paths: learningPaths.value,
      no_result_message: learningNoResultMsg.value,
      max_path_depth: maxPathDepth.value,
      node_count: learningNodeCount.value
    },
    shortest: {
      start: pathStart.value,
      end: pathEnd.value,
      depth: shortestDepth.value,
      result: shortestResult.value,
      no_result_message: shortestNoResultMsg.value,
      start_name: shortestStartName.value,
      end_name: shortestEndName.value,
      steps: shortestPathSteps.value
    },
    dependency: {
      target: depTarget.value,
      target_name: depTargetName.value,
      depth: depDepth.value,
      result: depResult.value
    }
  }
  try {
    sessionStorage.setItem(PATH_WORKSPACE_KEY, JSON.stringify(workspace))
  } catch (error) {
    console.warn('[path] 保存页面工作区失败:', error)
  }
}

function restorePathWorkspace() {
  const workspace = readPathWorkspace()
  if (!workspace) return

  const plan = workspace.plan || {}
  const learning = workspace.learning || {}
  const shortest = workspace.shortest || {}
  const dependency = workspace.dependency || {}

  activeMode.value = ['plan', 'learning', 'shortest', 'dependency'].includes(workspace.active_mode)
    ? workspace.active_mode
    : 'plan'
  planTarget.value = plan.target || ''
  planDepth.value = Number(plan.depth) || 6
  planQuestionsPerStep.value = Number.isInteger(Number(plan.questions_per_step))
    ? Number(plan.questions_per_step)
    : 3
  planDifficultyPreference.value = ['foundation', 'balanced', 'challenge'].includes(plan.difficulty_preference)
    ? plan.difficulty_preference
    : 'balanced'
  planResult.value = plan.result || null
  planNoResultMsg.value = plan.no_result_message || ''
  planDoneSet.value = new Set()

  learningTarget.value = learning.target || ''
  learningTargetName.value = learning.target_name || ''
  learningDepth.value = Number(learning.depth) || 4
  learningPaths.value = Array.isArray(learning.paths) ? learning.paths : []
  learningNoResultMsg.value = learning.no_result_message || ''
  maxPathDepth.value = Number(learning.max_path_depth) || 0
  learningNodeCount.value = Number(learning.node_count) || 0

  pathStart.value = shortest.start || ''
  pathEnd.value = shortest.end || ''
  shortestDepth.value = Number(shortest.depth) || 5
  shortestResult.value = shortest.result || null
  shortestNoResultMsg.value = shortest.no_result_message || ''
  shortestStartName.value = shortest.start_name || ''
  shortestEndName.value = shortest.end_name || ''
  shortestPathSteps.value = Array.isArray(shortest.steps) ? shortest.steps : []

  depTarget.value = dependency.target || ''
  depTargetName.value = dependency.target_name || ''
  depDepth.value = Number(dependency.depth) || 4
  depResult.value = dependency.result || null
  masteredSet.value = new Set(getMastered())

  if (planResult.value?.target?.id) {
    const stepIds = new Set((planResult.value.steps || []).map(step => step.id))
    planDoneSet.value = new Set(
      getPlanDone(planResult.value.target.id).filter(nodeId => stepIds.has(nodeId))
    )
  }
}

function hydrateWorkspaceOptions() {
  const findNode = value => allKnowledgePoints.value.find(node =>
    (node.id || node.node_id) === value || node.name === value
  )
  const toOption = node => node && ({
    id: node.id || node.node_id,
    name: node.name,
    type: node.type || node.node_type || 'KnowledgeNode'
  })
  const shared = [
    toOption(findNode(planTarget.value)),
    toOption(findNode(learningTarget.value)),
    toOption(findNode(depTarget.value))
  ].filter(Boolean)
  knowledgeOptions.value = [...new Map(shared.map(option => [option.id, option])).values()]
  const startOption = toOption(findNode(pathStart.value))
  const endOption = toOption(findNode(pathEnd.value))
  startOptions.value = startOption ? [startOption] : []
  endOptions.value = endOption ? [endOption] : []
}

async function applyPlanRouteTarget() {
  const requestedTarget = String(route.query.target || '').trim()
  if (!requestedTarget) return false

  const node = allKnowledgePoints.value.find(item => {
    const id = String(item.id || item.node_id || '')
    return id === requestedTarget || String(item.node_id || '') === requestedTarget || item.name === requestedTarget
  })
  if (!node) {
    ElMessage.warning('未找到仪表盘推荐的知识点')
    return false
  }

  const option = {
    id: node.id || node.node_id,
    name: node.name,
    type: node.type || node.node_type || 'KnowledgeNode'
  }
  knowledgeOptions.value = [
    option,
    ...knowledgeOptions.value.filter(item => item.id !== option.id)
  ]
  activeMode.value = 'plan'
  planTarget.value = node.name
  planResult.value = null
  planNoResultMsg.value = ''
  planDoneSet.value = new Set()
  hasResult.value = false

  if (String(route.query.auto || '') === '1') {
    await generatePlanList()
  }
  return true
}

function destroyModeNetwork(mode) {
  if (mode === 'learning' && learningNetwork) {
    learningNetwork.destroy()
    learningNetwork = null
  }
  if (mode === 'shortest' && shortestNetwork) {
    shortestNetwork.destroy()
    shortestNetwork = null
  }
  if (mode === 'dependency' && depNetwork) {
    depNetwork.destroy()
    depNetwork = null
  }
}

function modeHasResult(mode) {
  if (mode === 'plan') return Boolean(planResult.value || planNoResultMsg.value)
  if (mode === 'learning') return learningPaths.value.length > 0 || Boolean(learningNoResultMsg.value)
  if (mode === 'shortest') return Boolean(shortestResult.value || shortestNoResultMsg.value)
  return Boolean(depResult.value)
}

async function restoreActiveModeView() {
  hasResult.value = modeHasResult(activeMode.value)
  showLegend.value = activeMode.value !== 'plan' && hasResult.value
  if (!hasResult.value) return
  await nextTick()
  if (activeMode.value === 'learning' && learningPaths.value.length) renderLearningPath()
  if (activeMode.value === 'shortest' && shortestResult.value) renderShortestPath()
  if (activeMode.value === 'dependency' && depResult.value) renderDependencyGraph(depTargetName.value)
}

watch(activeMode, async (mode, previousMode) => {
  destroyModeNetwork(previousMode)
  if (!restoringWorkspace) persistPathWorkspace()
  await restoreActiveModeView()
})

watch([
  planTarget, planDepth, planQuestionsPerStep, planDifficultyPreference,
  planResult, planNoResultMsg, planDoneSet,
  learningTarget, learningTargetName, learningDepth, learningPaths, learningNoResultMsg,
  pathStart, pathEnd, shortestDepth, shortestResult, shortestNoResultMsg,
  depTarget, depTargetName, depDepth, depResult
], persistPathWorkspace, { deep: true })

onMounted(async () => {
  restoringWorkspace = true
  restorePathWorkspace()
  await Promise.all([loadAllKnowledge(), loadLearningState({ force: true })])
  masteredSet.value = new Set(getMastered())
  if (planResult.value?.revision !== getRevision()) {
    planResult.value = null
    planDoneSet.value = new Set()
  }
  hydrateWorkspaceOptions()
  restoringWorkspace = false
  await applyPlanRouteTarget()
  await restoreActiveModeView()
  persistPathWorkspace()
})

onUnmounted(() => {
  persistPathWorkspace()
  if (learningNetwork) learningNetwork.destroy()
  if (shortestNetwork) shortestNetwork.destroy()
  if (depNetwork) depNetwork.destroy()
  learningNetwork = null
  shortestNetwork = null
  depNetwork = null
})
</script>

<style scoped>
.path-page {
  height: calc(100vh - 120px);
  display: flex;
  flex-direction: column;
  background: #f5f7fa;
}

.page-header {
  background: white;
  padding: 12px 20px;
  border-bottom: 1px solid #e4e7ed;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.header-left h2 {
  margin: 0;
  font-size: 18px;
  color: #303133;
}


.mode-switch {
  margin-left: auto;
}

.main-area {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* 左侧控制面板 */
.control-panel {
  width: 320px;
  min-width: 320px;
  background: white;
  border-right: 1px solid #e4e7ed;
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel-section {
  padding: 0;
}

.panel-section h4 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px 0;
  font-size: 15px;
  color: #303133;
}

.panel-desc {
  font-size: 12px;
  color: #909399;
  margin: 0 0 12px 0;
  line-height: 1.5;
}

.full-width {
  width: 100%;
}

.param-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 12px 0 4px 0;
  font-size: 13px;
  color: #606266;
}

.depth-hint {
  font-size: 11px;
  color: #909399;
  margin-bottom: 8px;
  text-align: right;
}

.path-selector {
  margin-bottom: 8px;
}

.path-selector label {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.path-arrow {
  text-align: center;
  color: #909399;
  margin: 4px 0;
}

.option-type {
  float: right;
  color: #909399;
  font-size: 12px;
}

/* 依赖结果 */
.dep-result {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 12px;
}

.dep-block h4 {
  font-size: 13px;
  margin-bottom: 8px;
}

.dep-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.dep-tag {
  cursor: pointer;
}

.empty-tip {
  font-size: 12px;
  color: #c0c4cc;
}

/* 图例 */
.legend-section {
  margin-top: auto;
}

.legend-section h4 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  margin-bottom: 10px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #606266;
  margin-bottom: 6px;
}

.legend-edge {
  margin-bottom: 4px;
}

.legend-dot {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  display: inline-block;
  flex-shrink: 0;
}

.legend-dot.target { background: #f56c6c; border: 2px solid #c0392b; }
.legend-dot.start { background: #67c23a; border: 2px solid #529b2e; }
.legend-dot.middle { background: #e6a23c; }
.legend-dot.depth1 { background: #e6a23c; }
.legend-dot.depth2 { background: #409eff; }
.legend-dot.foundation { background: #67c23a; }
.legend-dot.relate { background: #409eff; }
.legend-dot.prereq-dot { background: #e6a23c; }
.legend-dot.next-dot { background: #67c23a; }

.legend-line {
  width: 20px;
  height: 2px;
  display: inline-block;
  flex-shrink: 0;
}
.legend-line.solid { background: #409eff; }
.legend-line.dashed {
  background: repeating-linear-gradient(90deg, #c0c4cc 0px, #c0c4cc 4px, transparent 4px, transparent 6px);
}
.legend-line.legend-rel-prereq { background: #e6a23c; }
.legend-line.legend-rel-core { background: #409eff; }
.legend-line.legend-rel-other { background: #909399; }

.legend-arrow {
  width: 20px;
  height: 2px;
  display: inline-block;
  flex-shrink: 0;
  position: relative;
}
.legend-arrow::after {
  content: '→';
  position: absolute;
  right: -8px;
  top: -7px;
  font-size: 10px;
}
.legend-arrow.prereq-arr { background: #e6a23c; }
.legend-arrow.prereq-arr::after { color: #e6a23c; }
.legend-arrow.next-arr { background: #67c23a; }
.legend-arrow.next-arr::after { color: #67c23a; }

/* 右侧可视化 */
.visual-area {
  flex: 1;
  background: #f5f7fa;
  position: relative;
  overflow: hidden;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
}

.empty-state h3 {
  margin: 16px 0 8px 0;
  color: #606266;
}

.empty-state p {
  margin: 0 0 20px 0;
  font-size: 14px;
}

.empty-tips {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 13px;
}

.result-area {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* 学习计划清单 */
.plan-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px 20px 20px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.plan-step {
  background: white;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px 16px;
  transition: box-shadow 0.2s, opacity 0.2s;
}

.plan-step:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.plan-step-done {
  opacity: 0.55;
  background: #f0f9eb;
}

.plan-step-target {
  border: 2px solid #f56c6c;
}

.plan-step-main {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.plan-step-order {
  min-width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #409eff;
  color: white;
  font-size: 13px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.plan-step-target .plan-step-order {
  background: #f56c6c;
}

.plan-step-body {
  flex: 1;
  min-width: 0;
}

.plan-step-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.plan-step-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  cursor: pointer;
}

.plan-step-name:hover {
  color: #409eff;
  text-decoration: underline;
}

.plan-step-prereq {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.plan-questions {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-top: 1px dashed #e4e7ed;
  padding-top: 8px;
}

.plan-question {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.q-difficulty {
  flex-shrink: 0;
  width: 42px;
  text-align: center;
}

.q-name {
  color: #606266;
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

a.q-name:hover {
  color: #409eff;
  text-decoration: underline;
}

.q-pass {
  font-size: 12px;
  color: #c0c4cc;
  flex-shrink: 0;
}

.plan-mastered-btn {
  flex-shrink: 0;
  margin-top: 2px;
}

.plan-progress-section {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 12px;
}

.plan-progress-tips {
  font-size: 11px;
  color: #909399;
  margin-top: 8px;
  line-height: 1.5;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 20px;
  background: white;
  border-bottom: 1px solid #e4e7ed;
  font-size: 14px;
  color: #606266;
  flex-wrap: wrap;
  gap: 8px;
}

.result-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.result-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.result-header-right {
  font-size: 13px;
  color: #909399;
}

.graph-container {
  flex: 1;
  background: white;
  margin: 12px;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  overflow: hidden;
}

/* 最短路径布局：图 + 步骤面板并排 */
.shortest-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.path-steps-panel {
  width: 220px;
  min-width: 220px;
  background: white;
  border-left: 1px solid #e4e7ed;
  padding: 12px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.path-steps-panel h4 {
  margin: 0 0 8px 0;
  font-size: 13px;
  color: #303133;
}

.path-step {
  display: flex;
  flex-direction: column;
}

.step-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 4px;
  background: #f5f7fa;
  font-size: 12px;
}

.step-node.step-start {
  background: #e8f5e9;
  border: 1px solid #a5d6a7;
}

.step-node.step-end {
  background: #ffebee;
  border: 1px solid #ef9a9a;
}

.step-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #909399;
  flex-shrink: 0;
}

.step-start .step-dot { background: #67c23a; }
.step-end .step-dot { background: #f56c6c; }

.step-name {
  flex: 1;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-rel {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px 2px 24px;
  font-size: 11px;
  color: #909399;
}

.step-arrow {
  font-size: 10px;
  color: #c0c4cc;
}

.no-result {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #909399;
  gap: 12px;
}

.no-result p {
  font-size: 14px;
  color: #606266;
  text-align: center;
  max-width: 300px;
  line-height: 1.6;
}

/* 响应式 */
@media (max-width: 900px) {
  .main-area {
    flex-direction: column;
  }
  .control-panel {
    width: 100%;
    min-width: auto;
    max-height: 300px;
  }
}
</style>
