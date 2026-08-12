import axios from 'axios'
import { ElMessage } from 'element-plus'

// 创建axios实例
const request = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
request.interceptors.request.use(
  config => {
    return config
  },
  error => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  response => {
    const res = response.data
    
    // 如果响应码不是200，判断为错误
    if (response.status !== 200) {
      ElMessage.error(res.message || '请求失败')
      return Promise.reject(new Error(res.message || '请求失败'))
    }
    
    return res
  },
  error => {
    if (axios.isCancel(error)) {
      return Promise.reject(error)
    }
    console.error('响应错误:', error)
    
    let message = '网络错误'
    
    if (error.response) {
      // 后端可能返回非 JSON（如网关错误页），data 未必是对象，需安全取值
      const data = error.response.data
      const serverMessage = (data && typeof data === 'object' && typeof data.message === 'string')
        ? data.message
        : ''
      switch (error.response.status) {
        case 400:
          message = '请求参数错误'
          break
        case 404:
          message = '资源不存在'
          break
        case 500:
          message = '服务器错误'
          break
        default:
          message = serverMessage || '请求失败'
      }
    }
    
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

export default request
