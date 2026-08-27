# Influencer Distortion Detection — 完整项目

前端 + 后端本地一键启动指南。

## 目录结构

```
distortion-backend/        ← 后端 (FastAPI + Python)
  app/
    api/routes.py          ← 所有 REST 端点
    core/database.py       ← SQLite 数据库连接
    models/db.py           ← ORM 表定义
    services/
      scraper.py           ← Nitter 抓取器
      classifier.py        ← 关键词规则 + Claude LLM 分类
      aggregator.py        ← 90天窗口聚合
      pipeline.py          ← 五步流水线编排
    main.py                ← FastAPI 入口
  requirements.txt
  .env                     ← 配置（复制后填写）

index.html                 ← 前端（已对接真实 API）
```

---

## 快速启动

### 1. 安装依赖

```bash
cd distortion-backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env .env.local
# 编辑 .env，填入 ANTHROPIC_API_KEY（可选）
# NITTER_INSTANCES 默认已填好公开实例，可以直接用
```

### 3. 启动后端

```bash
cd distortion-backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

看到以下输出说明成功：
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

API 文档自动生成：http://localhost:8000/docs

### 4. 启动前端（另开一个终端）

```bash
cd influencer-distortion-tool
python3 -m http.server 8080
```

访问 http://localhost:8080

---

## 使用流程

1. 在搜索框输入 `@某人的handle`，点 **Analyze**
2. 后端开始抓取（~10-30秒，取决于 Nitter 响应速度）
3. 完成后 Profile tab 自动更新为真实数据
4. 切换到 **Flagged posts** 查看分类结果和置信度
5. **Research** tab 可以做人工标注和导出数据

---

## API 端点速查

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/analyze/{handle}` | 触发完整流水线分析 |
| GET  | `/api/profile/{handle}` | 获取最新缓存档案 |
| GET  | `/api/posts/{handle}` | 帖子列表，支持过滤 |
| GET  | `/api/watchlist` | 全部追踪账号 |
| POST | `/api/watchlist` | 添加账号 |
| POST | `/api/annotate/{post_id}` | 人工标注 |
| GET  | `/api/annotation-queue/{handle}` | 待标注队列 |
| POST | `/api/behavior-log` | 行为意向记录 |
| GET  | `/api/export/{handle}/jsonl` | 导出语料 |
| GET  | `/health` | 健康检查 |

---

## 注意事项

- **Nitter 实例可能不稳定**。如果抓取失败，换一个实例填入 `.env` 的 `NITTER_INSTANCES`。  
  公开实例列表：https://github.com/zedeus/nitter/wiki/Instances

- **LLM 分类可选**。不填 `ANTHROPIC_API_KEY` 也能运行，只用关键词规则分类，置信度略低。

- **数据库**文件在 `distortion-backend/data/distortion.db`，SQLite 格式，可用 DB Browser for SQLite 查看。
