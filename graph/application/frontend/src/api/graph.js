import request from './index'

/**
 * 获取图谱数据
 * @param {number} limit - 节点数量限制
 * @returns {Promise}
 */
export function getGraphData(limit = 2000, nodeTypes = null) {
  return request({
    url: '/graph/data',
    method: 'get',
    params: { 
      limit,
      node_types: nodeTypes ? nodeTypes.join(',') : null
    }
  })
}

/**
 * 获取统计信息
 * @returns {Promise}
 */
export function getStatistics() {
  return request({
    url: '/graph/statistics',
    method: 'get'
  })
}

/**
 * 获取节点详情
 * @param {string} nodeId - 节点ID
 * @param {string} direction - 关系方向（in/out/both）
 * @returns {Promise}
 */
export function getNodeDetail(nodeId, direction = 'both') {
  return request({
    url: `/graph/node/${nodeId}`,
    method: 'get',
    params: { direction }
  })
}

export function getNodeNeighbors(nodeId, limit = 30, relationshipTypes = []) {
  return request({
    url: `/graph/node/${encodeURIComponent(nodeId)}/neighbors`,
    method: 'get',
    params: {
      limit,
      relationship_types: relationshipTypes.length ? relationshipTypes.join(',') : null
    }
  })
}

export function getGraphFragment(nodeIds, relationshipTypes = []) {
  return request({
    url: '/graph/nodes/fragment',
    method: 'post',
    data: {
      node_ids: nodeIds,
      relationship_types: relationshipTypes
    }
  })
}

/**
 * 获取所有节点标签
 * @returns {Promise}
 */
export function getLabels() {
  return request({
    url: '/graph/labels',
    method: 'get'
  })
}

/**
 * 获取所有关系类型
 * @returns {Promise}
 */
export function getRelationshipTypes() {
  return request({
    url: '/graph/relationship-types',
    method: 'get'
  })
}

/**
 * 获取知识点关联的题目
 * @param {string} knowledgeId - 知识点ID或名称
 * @param {number} limit - 返回数量限制
 * @returns {Promise}
 */
export function getQuestionsByKnowledge(knowledgeId, limit = 10) {
  return request({
    url: `/graph/knowledge-point/${encodeURIComponent(knowledgeId)}/questions`,
    method: 'get',
    params: { limit }
  })
}

/**
 * 获取题目关联的所有知识点
 * @param {string} questionId - 题目业务ID
 * @returns {Promise}
 */
export function getKnowledgeByQuestion(questionId) {
  return request({
    url: `/graph/question/${questionId}/knowledge`,
    method: 'get'
  })
}

/**
 * 获取题目与知识点匹配的统计信息
 * @returns {Promise}
 */
export function getQuestionKnowledgeStatistics() {
  return request({
    url: '/graph/question-knowledge/statistics',
    method: 'get'
  })
}

/**
 * 获取所有知识点列表
 * @param {number} limit - 返回数量限制
 * @param {string} nodeType - 节点类型过滤
 * @param {number} chapterId - 章节ID过滤
 * @returns {Promise}
 */
export function getKnowledgePoints(limit = 1000, nodeType = null, chapterId = null) {
  return request({
    url: '/graph/knowledge-points',
    method: 'get',
    params: { limit, node_type: nodeType, chapter_id: chapterId }
  })
}

export function getKnowledgePointPage(params, signal) {
  return request({
    url: '/graph/knowledge-points/page',
    method: 'get',
    params,
    signal
  })
}

/**
 * 获取知识点详情
 * @param {string} knowledgeId - 知识点ID
 * @returns {Promise}
 */
export function getKnowledgePointDetail(knowledgeId) {
  return request({
    url: `/graph/knowledge-point/${knowledgeId}`,
    method: 'get'
  })
}

/**
 * 获取题目列表（分页）
 * @param {number} page - 页码
 * @param {number} pageSize - 每页数量
 * @param {string} difficulty - 难度筛选
 * @param {string} category1 - 一级分类筛选
 * @param {string} keyword - 关键词搜索
 * @param {string} sortBy - 排序方式（id, difficulty, kp_count）
 * @returns {Promise}
 */
export function getQuestions(page = 1, pageSize = 20, difficulty = null, category1 = null, keyword = null, sortBy = 'id') {
  return request({
    url: '/graph/questions',
    method: 'get',
    params: { page, page_size: pageSize, difficulty, category1, keyword, sort_by: sortBy }
  })
}

/**
 * 获取题目分类信息
 * @returns {Promise}
 */
export function getQuestionCategories() {
  return request({
    url: '/graph/questions/categories',
    method: 'get'
  })
}

/**
 * 获取题目详情
 * @param {string} questionId - 题目ID
 * @returns {Promise}
 */
export function getQuestionDetail(questionId) {
  return request({
    url: `/graph/question/${questionId}`,
    method: 'get'
  })
}

/**
 * 获取首页展示数据
 * @returns {Promise}
 */
export function getHomeData() {
  return request({
    url: '/graph/home/data',
    method: 'get'
  })
}
