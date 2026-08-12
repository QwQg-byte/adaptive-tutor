import request from './index'

/**
 * 查找最短路径
 * @param {Object} data - 路径数据
 * @param {string} data.start - 起始节点
 * @param {string} data.end - 目标节点
 * @param {number} data.maxDepth - 最大深度
 * @returns {Promise}
 */
export function findShortestPath(data) {
  return request({
    url: '/path/shortest',
    method: 'post',
    data
  })
}

/**
 * 获取学习路径
 * @param {string} knowledgeName - 知识点名称
 * @param {number} maxDepth - 最大深度
 * @returns {Promise}
 */
export function getLearningPath(knowledgeName, maxDepth = 3) {
  return request({
    url: `/path/learning/${knowledgeName}`,
    method: 'get',
    params: { max_depth: maxDepth }
  })
}

/**
 * 获取相关节点
 * @param {string} nodeId - 节点ID
 * @param {number} limit - 返回数量限制
 * @returns {Promise}
 */
export function getRelatedNodes(nodeId, limit = 20) {
  return request({
    url: `/path/related/${nodeId}`,
    method: 'get',
    params: { limit }
  })
}

/**
 * 获取依赖关系
 * @param {string} knowledgeName - 知识点名称
 * @param {number} depth - 追溯深度，默认4
 * @returns {Promise}
 */
export function getDependencies(knowledgeName, depth = 4) {
  return request({
    url: `/path/dependencies/${knowledgeName}`,
    method: 'get',
    params: { depth }
  })
}

/**
 * 生成学习计划（拓扑排序的线性学习清单 + 配套练习题）
 * @param {Object} data
 * @param {string} data.target - 目标知识点名称或业务ID（如 NODE_358）
 * @param {number} data.max_depth - 前置依赖追溯深度
 * @param {string[]} data.mastered - 已掌握知识点的业务ID列表
 * @param {number} data.questions_per_step - 每步推荐题目数
 * @returns {Promise}
 */
export function generatePlan(data) {
  return request({
    url: '/path/plan',
    method: 'post',
    data
  })
}
