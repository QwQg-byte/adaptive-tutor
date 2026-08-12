import request from './index'

/**
 * 搜索节点（POST）
 * @param {Object} data - 搜索数据
 * @param {string} data.keyword - 关键词
 * @param {Array} data.nodeTypes - 节点类型
 * @param {number} data.limit - 返回数量限制
 * @returns {Promise}
 */
export function searchNodes(data) {
  return request({
    url: '/search/',
    method: 'post',
    data
  })
}

/**
 * 关键词搜索（GET）
 * @param {Object} params - 搜索参数
 * @param {string} params.keyword - 关键词
 * @param {string} params.nodeType - 节点类型
 * @param {number} params.limit - 返回数量限制
 * @returns {Promise}
 */
export function searchByKeyword(params, signal) {
  return request({
    url: '/search/keyword',
    method: 'get',
    params,
    signal
  })
}

/**
 * 获取搜索建议
 * @param {Object} params - 搜索参数
 * @param {string} params.keyword - 关键词
 * @param {number} params.limit - 返回数量限制
 * @returns {Promise}
 */
export function getSearchSuggestions(params, signal) {
  return request({
    url: '/search/suggestions',
    method: 'get',
    params,
    signal
  })
}

/**
 * 获取业务节点类型标签
 * @returns {Promise}
 */
export function getLabels() {
  return request({
    url: '/search/labels',
    method: 'get'
  })
}
