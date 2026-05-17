# QED-Tracker v0.2 任务清单

## 第一阶段：架构重构（已完成 ✅ 迁移至 resolved.md）

## 第二阶段：功能延续（后续）

| ID | 类型 | 描述 | 优先级 | 状态 |
|----|------|------|--------|------|
| T-201 | 执行 | 补齐缺失教材 (熊金城, Stein RA/CA, Evans PDE 等 9 本) | P1 | ⬜ |
| T-202 | 执行 | 按领域检索 arXiv 论文 (math.CA/FA/AP/CV) | P2 | ⬜ |
| T-203 | 执行 | 官方文档镜像 wget --mirror (pytorch/sklearn/xgboost/yolo) | P2 | 🔄 |
| T-204 | 功能 | resources 表对接 (博客/视频/项目链接) | P3 | ⬜ |
| T-205 | 功能 | GitHub 项目检索 (入 resources 表) | P3 | ⬜ |
| T-206 | 讨论 | ⚠️ 大模型方向 — 确定具体资料清单 | 待定 | ⬜ |

## 第三阶段：大模型方向（预留）

| ID | 类型 | 描述 | 优先级 |
|----|------|------|--------|
| T-301 | 内容 | 填写 `curricula/llm_research.py` — 定义 GitHub 仓库/arXiv 领域/文档目标 | 待定 |
| T-302 | 执行 | 大模型方向首次采集 | 待定 |

## T-203 进度

| 步骤 | 状态 |
|------|------|
| `app/tools/wget_mirror.py` 新建 | ✅ |
| `app/collectors/doc_scraper.py` 改为 wget 方案 | ✅ |
| xgboost 镜像验证 (276 files, 11MB) | ✅ |
| sklearn 镜像 | 🔄 (运行中, 203 files, 17.8MB) |
| pytorch 镜像 | ⬜ |
| yolo 镜像 | ⬜ |
