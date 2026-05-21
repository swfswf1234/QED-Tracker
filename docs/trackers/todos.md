# QED-Tracker v0.2 任务清单

## 第一阶段：架构重构（已完成 ✅ 迁移至 resolved.md）

## 第二阶段：功能延续（后续）

| ID | 类型 | 描述 | 优先级 | 状态 |
|----|------|------|--------|------|
| T-201 | 执行 | 补齐缺失教材 (熊金城, Stein RA/CA, Evans PDE 等 9 本) | P1 | ⬜ (LibGen 搜索可达但下载失败，需替代源) |
| T-202 | 执行 | 按领域检索 arXiv 论文 (math.CA/FA/AP/CV) | P2 | ⬜ |
| T-203 | 执行 | 官方文档镜像 wget --mirror (pytorch/sklearn/xgboost/yolo) | P2 | 🔄 |
| T-204 | 功能 | Resources Hub: resources 表对接、查询、收藏、导出 | P3 | 🔄 |
| T-205 | 功能 | GitHub 项目检索 (入 resources 表) | P3 | 🔄 |
| T-206 | 讨论 | ⚠️ 大模型方向 — 确定具体资料清单 | 待定 | ⬜ |

## T-204 进度

| 子任务 | 状态 |
|--------|------|
| `app/tools/rss_tracker.py` — Quanta REST + Tao RSS 抓取 | ✅ |
| `app/collectors/frontier_collector.py` — 编排/去重/入库 | ✅ |
| `scripts/hunt_frontier.py` — CLI 入口 | ✅ |
| `app/repository/resource_repo.py` — URL 去重、搜索、收藏查询 | ✅ |
| `scripts/manage_resources.py` — list/search/favorite/export CLI | ✅ |
| `docs/design/resources_hub.md` — 资源中心设计 | ✅ |
| 种子数据首次入库 (`--seed`) | 🔄 代码就绪，需 MySQL 运行后执行 |
| LLM 摘要 (`--summary`) | ⬜ 预留

## T-205 进度

| 子任务 | 状态 |
|--------|------|
| `app/tools/github_downloader.py` — GitHub API 元数据工具 | ✅ |
| `app/collectors/github_collector.py` — GitHub repo 元数据入 resources | ✅ |
| `scripts/hunt_github.py` — repo 参数/文件输入 CLI | ✅ |
| LLM 清单批量接入 | ⬜ |

## 第三阶段：大模型方向（预留）

| ID | 类型 | 描述 | 优先级 |
|----|------|------|--------|
| T-301 | 内容 | 填写 `curricula/llm_research.py` — 定义 GitHub 仓库/arXiv 领域/文档目标 | 待定 |
| T-302 | 执行 | 大模型方向首次采集 | 待定 |

## T-203 进度

| 步骤 | 状态 |
|------|------|
| `app/tools/wget_mirror.py` 新建 + wait 参数 | ✅ |
| `app/collectors/doc_scraper.py` 改为 wget 方案 + 每源独立 wait | ✅ |
| `app/tools/serve_docs.py` 本地 HTTP 文档查看服务 | ✅ |
| xgboost 镜像 (276 files, 11MB) | ✅ |
| sklearn 镜像 (203 files, 17.8MB) | ✅ |
| pytorch 镜像 (1549 files, 322MB) | ✅ |
| yolo 镜像 (1751 files, 534MB, partial) | ⚠️ 2h 超时 |

### 已知遗留问题

- **YOLO 镜像超时**：`docs.ultralytics.com` 使用 Next.js，wget 可能陷入无限递归。当前已下载 1751 文件足够浏览，如需完整镜像需改用 httpx+BS4 方案
- **CDN 外部资源**：PyTorch 的 Sphinx 主题引用了 Google Fonts 等 CDN 资源，wget 无法抓取，打开页面时需联网加载这些外部资源
- **PyTorch 版本号**：当前镜像指向 `docs/2.12/`，版本更新后需手动更新 URL
