# 下载流程与登记设计

状态：Draft
任务类型：B
最后更新：2026-09-01
需求方：QED-Engine（REQ-026/REQ-032）
目标项目：QED-Tracker
评审方：用户

## 背景

QED-Tracker 的下载能力覆盖两条路径：
- **自动下载**：LLM 探索推荐 → 候选评估 → 渠道下载 → PDF 校验 → 去重落盘
- **手动导入**：用户本地 PDF → inspect → 去重 → 原子落盘（详见 [knowledge-import.md](2026-09-knowledge-import.md)）

两条路径最终汇入同一验收登记流程：verify → approve → 复制到根数据集 + 登记同步。

## 当前实现

### 三条触发链路

| 链路 | 入口 | 触发方式 | 代码位置 |
|---|---|---|---|
| catalog run | 批量下载 | CLI/catalog 批处理 | `application/books.py` |
| mainline CLI | 单门课程下载 | `mainline download` | `cli.py` + `main_line/` |
| books API | 单本书下载 | `POST /books/{id}/fetch` | `api/main.py` |

### 自动下载流程

```
候选发现（providers/books.py）
  → 来源评估（source-discovery 矩阵）
  → 下载（downloader.py，retry/backoff）
  → PDF 校验（magic bytes + page count）
  → sha256 去重
  → 原子落盘（raw/ 目录）
  → 状态更新（candidate → downloaded）
  → 渠道记录（add_source）
```

代码位置：`downloader.py`（下载+校验）、`inventory.py`（去重+登记）、`application/books.py`（编排）

### 手动导入流程

```
用户提供 file_path + target_path
  → inspect_pdf（magic + pages）
  → sha256 去重
  → atomic move to raw/
  → complete_download（candidate → downloaded）
  → add_source（channel=local_import）
```

代码位置：`api/main.py` POST /books/{book_id}/import（line 770）

target_path 解析（D9）：期望路径不含 sha 后缀，落盘时自动追加 `_<sha8>`；fallback 路径 `raw/<domain_id>/<course_id>/<safe_name>_<sha8>.pdf`

### 验收登记流程

```
mainline verify（检查下载文件完整性）
  → mainline approve（复制到根数据集 + 登记同步）
  → channel stats 聚合（main_line/store.py）
```

代码位置：`cli.py`（mainline verify/approve/channels）、`main_line/store.py`（channel_stats）

### 状态机（qt_books）

```
candidate → downloading → downloaded → verified → approved → transferred
    ↓           ↓            ↓
  failed      failed      failed
```

### PDF 校验

| 检查项 | 说明 | 失败处理 |
|---|---|---|
| magic bytes | PDF 文件头校验 | 拒绝导入，返回错误 |
| page count | 至少 1 页 | 拒绝导入 |
| sha256 | 去重判定 | 已有则返回既有记录 |

### 渠道记录

每次下载/导入记录渠道信息（来源协议、下载时间、文件大小），用于 REQ-020② 找得率统计。

## 优化目标

| 优化项 | 目标 | 关联任务 |
|---|---|---|
| 三门基础课下载闭环 | 00/01/02 课程从探索到下载到验收全链路通过 | QED-050-D |
| 渠道记录完备 | 所有下载/导入路径均记录渠道信息 | QED-050-D |
| 失败重试策略 | 下载失败后的重试/降级机制验证 | QED-050-D |
| target_path 落盘验证 | D9 路径解析端到端验证 | QED-050-D |

## 测试覆盖

| 测试文件 | 覆盖内容 |
|---|---|
| `test_download_inventory.py` | 下载+库存全链路（候选→下载→去重→登记） |
| `test_services.py` | 服务层（下载编排+错误处理） |
| `test_knowledge_import.py` | 手动导入 6 用例 + G2 回写 |
| `test_main_line_cli.py` | mainline CLI（new/review/download/verify/approve/reject/channels） |

## 关联文档

| 文档 | 关系 |
|---|---|
| [knowledge-import.md](2026-09-knowledge-import.md) | 手动导入（本设计的手动路径） |
| [data-lifecycle.md](2026-09-data-lifecycle.md) | 数据生命周期（下载后的状态流转） |
| [download-flow.md](2026-08-download-flow.md) | 下载流程现状分析（三条链路+成功率） |
| `design/acquisition-and-inventory.md` | 资源获取与库存（Accepted） |
| `design/source-discovery.md` | 来源发现与评估矩阵（Accepted） |
| `design/main-line-curriculum.md` | 主链路设计（Accepted） |

## 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-09-01 | 初始创建 | 从 acquisition-and-inventory + download-flow + knowledge-dual-flow 整合 |
