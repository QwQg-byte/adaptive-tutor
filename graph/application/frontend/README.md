# 知识图谱可视化系统 - 前端

基于Vue 3 + vis-network的知识图谱可视化前端应用。

---

## 📋 功能特性

- ✅ 图谱可视化（vis-network）
- ✅ 智能搜索功能
- ✅ 学习路径规划
- ✅ 统计信息展示
- ✅ 响应式设计
- ✅ 节点详情查看
- ✅ 路径导航

---

## 🚀 快速开始

### 1. 安装依赖

```bash
cd application/frontend
npm install
# 或
yarn install
# 或
pnpm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

访问: http://localhost:5173

### 3. 构建生产版本

```bash
npm run build
```

构建结果在 `dist/` 目录

---

## 📁 项目结构

```
frontend/
├── src/
│   ├── api/              # API接口
│   │   ├── index.js     # Axios实例
│   │   ├── graph.js     # 图谱API
│   │   ├── search.js    # 搜索API
│   │   └── path.js      # 路径API
│   ├── components/       # 组件
│   ├── views/           # 页面
│   │   ├── Home.vue     # 首页
│   │   ├── GraphPage.vue # 图谱页面
│   │   ├── SearchPage.vue # 搜索页面
│   │   └── PathPage.vue # 路径页面
│   ├── router/           # 路由
│   ├── assets/          # 静态资源
│   ├── App.vue          # 根组件
│   └── main.js          # 入口文件
├── package.json
├── vite.config.js
├── index.html
└── README.md
```

---

## 🎨 页面说明

### 1. 首页 (`/`)
- 系统概览
- 统计信息展示
- 功能入口

### 2. 图谱浏览 (`/graph`)
- 知识图谱可视化
- 节点筛选
- 节点详情查看
- 图谱统计信息
- 默认加载 200 个节点，双击节点或点击“展开邻居”按需加载局部图谱

### 3. 智能搜索 (`/search`)
- 关键词搜索
- 搜索建议
- 节点类型筛选
- 在图谱中查看

### 4. 学习路径 (`/path`)
- 路径规划
- 知识点依赖查询
- 路径可视化

知识浏览页使用服务端摘要分页，每页加载 30 条；章节、知识类型和关键词筛选均在
服务端执行。富文本通过 `marked` 解析并由 DOMPurify 清理后渲染。

---

## 🔧 技术栈

- **框架**: Vue 3 (Composition API)
- **构建工具**: Vite
- **UI组件库**: Element Plus
- **图谱可视化**: vis-network
- **HTTP客户端**: Axios
- **路由**: Vue Router 4

---

## 📦 主要依赖

```json
{
  "vue": "^3.3.11",
  "vue-router": "^4.2.5",
  "axios": "^1.6.2",
  "vis-network": "^9.1.13",
  "marked": "^18.0.6",
  "dompurify": "^3.4.12",
  "element-plus": "^2.4.4"
}
```

---

## 🔌 API集成

所有API请求都封装在 `src/api/` 目录下：

### 图谱API
```javascript
import { getGraphData, getNodeDetail } from '@/api/graph'

// 获取图谱数据
const data = await getGraphData(1000)

// 获取节点详情
const detail = await getNodeDetail(nodeId)
```

### 搜索API
```javascript
import { searchByKeyword } from '@/api/search'

// 搜索
const results = await searchByKeyword({
  keyword: '动态规划',
  node_types: ['Algorithm'],
  limit: 100
})
```

### 路径API
```javascript
import { findShortestPath } from '@/api/path'

// 查找路径
const path = await findShortestPath({
  start: '两数之和',
  end: '最长子序列',
  max_depth: 5
})
```

---

## 🎨 组件使用

### vis-network

图谱可视化使用vis-network库：

```javascript
import { DataSet, Network } from 'vis-network'

// 创建数据集
const nodes = new DataSet([...])
const edges = new DataSet([...])

// 创建图谱
const network = new Network(container, { nodes, edges }, options)

// 事件监听
network.on('click', (params) => {
  console.log('点击节点:', params.nodes)
})
```

### Element Plus

UI组件使用Element Plus：

```vue
<template>
  <el-button type="primary" @click="handleClick">
    点击我
  </el-button>
</template>

<script setup>
import { ElMessage } from 'element-plus'

function handleClick() {
  ElMessage.success('操作成功')
}
</script>
```

---

## 🔍 调试

### 开发工具
- Vue DevTools: 浏览器扩展
- Network: 查看API请求
- Console: 查看日志

### 代理配置

在`vite.config.js`中配置API代理：

```javascript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true
    }
  }
}
```

---

## 📱 响应式设计

- 桌面: >1200px
- 平板: 768px - 1200px
- 手机: <768px

---

## 🧪 测试

```bash
# 运行一次性测试
npm run test:run

# 运行 ESLint
npm run lint

# 生产构建
npm run build
```

---

## 📦 部署

### Nginx配置

```nginx
server {
    listen 80;
    server_name example.com;

    root /var/www/knowledge-frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 🐛 常见问题

### 1. vis-network无法加载
确保已安装vis-network包：
```bash
npm install vis-network
```

### 2. API请求失败
检查后端服务是否启动，检查代理配置。

### 3. 样式加载问题
确保Element Plus样式已导入：
```javascript
import 'element-plus/dist/index.css'
```

---

## 📝 开发规范

### 命名规范
- 组件: PascalCase
- 函数: camelCase
- 常量: UPPER_SNAKE_CASE

### 代码风格
- 使用Composition API
- 使用`<script setup>`
- 组件按功能拆分

---

## 📄 许可证

许可证和共同开发者署名尚待书面确认，当前版本不应声明为 MIT 开源发布。

---

## 👥 贡献

欢迎提交Issue和Pull Request。
