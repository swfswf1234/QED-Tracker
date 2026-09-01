# 数据生命周期设计

状态：Draft
任务类型：B
最后更新：2026-09-01
需求方：QED-Tracker（贯穿全流程）
目标项目：QED-Tracker
评审方：用户

## 背景

QED-Tracker 管理三类核心数据实体，各自有独立的生命周期：
- **知识**（qt_knowledge）：从 draft 到 transferred 的完整旅程
- **探索**（exploration_stage）：从未开始到已完成/失败的状态流转
- **书籍**（qt_books）：从 candidate 到 transferred 的下载登记链

三条生命周期相互交叉：探索结果触发知识创建，知识确认触发书籍下载，书籍验收触发登记移交。

## 当前实现

### 知识生命周期（qt_knowledge）

```
draft → confirmed → downloaded → verified → approved → transferred
  ↓         ↓           ↓          ↓
rejected  rejected    failed     rejected
```

| 阶段 | 触发条件 | 写主体 | 代码位置 |
|---|---|---|---|
| draft | 探索 adopt / 手动导入 | 8900 或本仓库 | `knowledge_repository.py` adopt_tutorials |
| confirmed | 用户确认 / 导入即确认 | 本仓库 8901 | `cli.py` knowledge confirm |
| downloaded | PDF 下载完成 | 本仓库 8901 | `inventory.py` complete_download |
| verified | mainline verify 通过 | 本仓库 8901 | `cli.py` mainline verify |
| approved | mainline approve 通过 | 本仓库 8901 | `cli.py` mainline approve |
| transferred | 复制到根数据集 + 登记 | 本仓库 8901 | `cli.py` mainline approve |

### 探索生命周期（exploration_stage）

```
未开始 → 已生成 → 探索中 → 待确认 → 已完成
                                  ↘ 失败
```

| 状态 | 写主体 | 触发条件 |
|---|---|---|
| 未开始→探索中 | 8900 | 探索任务启动 |
| 探索中→已生成 | 8900 | LLM 管线完成 |
| 已生成→待确认 | 8900 | 结果准备就绪 |
| 待确认→已完成 | 8901 | POST /apply-results |
| 待确认→探索中 | 8901 | POST /re-explore |
| 探索中→失败 | 8901 | lifespan 清理 |

### 书籍生命周期（qt_books）

```
candidate → downloading → downloaded → verified → approved → transferred
    ↓           ↓            ↓
  failed      failed      failed
```

| 阶段 | 触发条件 | 代码位置 |
|---|---|---|
| candidate | 探索推荐 / 手动添加 | `knowledge_repository.py` adopt_tutorials |
| downloading | 下载任务启动 | `downloader.py` |
| downloaded | PDF 校验通过 + sha256 去重 | `inventory.py` complete_download |
| verified | mainline verify 通过 | `cli.py` mainline verify |
| approved | mainline approve 通过 | `cli.py` mainline approve |
| transferred | 复制到根数据集 | `cli.py` mainline approve |

### 生命周期交叉点

```
exploration_stage=待确认
  → apply-results → exploration_stage=已完成
    → adopt tutorials → qt_knowledge=draft
      → confirm → qt_knowledge=confirmed
        → fetch PDF → qt_books=downloading → downloaded
          → verify → verified → approve → approved → transferred
            → qt_knowledge=transferred
```

### 清理策略

| 清理类型 | 触发条件 | 处理方式 |
|---|---|---|
| 启动清理（REQ-067-B10） | 服务启动时检测脏数据 | exploration_stage 异常值重置 |
| tmp 清理 | 下载完成/失败后 | 临时文件删除 |
| 失败态清理 | 探索/下载失败后 | 状态机回退到安全态 |

### 数据根规范

```
DATA_ROOT/
├── raw/                    # 下载的原始 PDF
│   ├── <domain_id>/
│   │   └── <course_id>/
│   │       └── <name>_<sha8>.pdf
├── docs/knowledge/         # 知识目录 JSON（docs/ 下，非数据根）
└── meta/                   # 已退役（REQ-032），不再使用
```

### 退役规则

- qt_resources：已退役（QED-030），旧表 drop，证据归档 `history/qed-030-retire-qt_resources/`
- meta/ JSON：已退役（REQ-032），元数据默认存数据库

## 优化目标

| 优化项 | 目标 | 关联任务 |
|---|---|---|
| 全状态路径测试 | 知识/探索/书籍三条生命周期各状态路径测试覆盖 | QED-050-E |
| 交叉点验证 | 探索→知识→书籍→登记全链路状态联动验证 | QED-050-E |
| 清理策略验证 | 启动清理 + tmp 清理 + 失败态清理端到端验证 | QED-050-E |
| 退役规则确认 | meta/ 退役 + qt_resources 退役无遗留引用 | QED-050-E |

## 测试覆盖

| 测试文件 | 覆盖内容 |
|---|---|
| `test_exploration_stage.py` | 6 态流转 + apply-results/re-explore |
| `test_knowledge_import.py` | 导入链 + G2 回写 + exploration_stage 联动 |
| `test_download_inventory.py` | 下载+库存全链路（candidate → downloaded） |
| `test_main_line_cli.py` | 验收登记（verify → approve → transferred） |
| `test_api.py` | API 端点状态变更 |
| `test_db_models.py` | ORM 模型字段完整性 |

## 关联文档

| 文档 | 关系 |
|---|---|
| [exploration-pipeline.md](2026-09-exploration-pipeline.md) | 探索管线（探索生命周期的驱动方） |
| [knowledge-import.md](2026-09-knowledge-import.md) | 手动导入（知识生命周期的手动入口） |
| [download-registration.md](2026-09-download-registration.md) | 下载登记（书籍生命周期的驱动方） |
| `architecture/shared-tables.md` | 共享表契约（状态机定义） |
| `architecture/database-schema.md` | 数据库 DDL（字段定义） |
| `design/service-lifecycle.md` | 服务生命周期（服务层，非数据层） |

## 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-09-01 | 初始创建 | 从 shared-tables + database-schema + main-line-curriculum 整合 |
