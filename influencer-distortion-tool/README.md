# Influencer Distortion Detection System

本地测试版前端 UI，对应系统设计文档 `influencer_distortion_system.docx`。

## 快速启动

直接用浏览器打开即可，**不需要任何构建工具**：

```bash
# 方式一：直接双击 index.html

# 方式二：用 Python 起一个本地服务（推荐，避免 CORS 问题）
python3 -m http.server 8080
# 然后访问 http://localhost:8080

# 方式三：用 Node.js
npx serve .
# 然后访问 http://localhost:3000
```

## 文件结构

```
influencer-distortion-tool/
└── index.html        # 全部代码，单文件
```

## 功能模块

| Tab | 内容 |
|-----|------|
| **Distortion profile** | 账号失真档案：四维指标卡、语言模式条形图、90天趋势折线图、关键洞察 |
| **Flagged posts** | 被标记的典型帖子，含失真类型标签 |
| **How it works** | 五步检测流水线说明 |
| **Watchlist** | 多账号监控列表，支持新增 |

## 交互说明

- **搜索框**：输入任意 @handle，点 Analyze 或按 Enter（Demo 模式只更新显示名，不调真实 API）
- **Add account**：在 Watchlist tab 点击，可新增账号到列表
- **深色模式**：跟随系统，自动切换

## 下一步接入真实数据

在 `index.html` 底部的 `runAnalysis()` 函数中替换 Demo 逻辑：

```javascript
async function runAnalysis() {
  const handle = document.getElementById('handle-input').value.trim();

  // 替换为你的后端 API
  const res = await fetch(`/api/profile?handle=${encodeURIComponent(handle)}`);
  const data = await res.json();

  // 更新各指标字段
  document.querySelector('.badge-score').textContent = data.distortionIndex;
  // ... 其他字段
}
```

## 系统设计对照

| 设计文档章节 | UI 对应位置 |
|------------|-----------|
| §3.1 Distortion Profile 五维度 | Profile tab 指标卡 + 条形图 |
| §4.2 Detection Pipeline | How it works tab |
| §1.1 Significance Inflation | `tag-inflate` 红色标签 |
| §1.2 Anxiety Manufacturing | `tag-anxiety` 橙色标签 |
| Novelty claim rate | `tag-novelty` 紫色标签 |
| Temporal distortion rate | `tag-temporal` 绿色标签 |
