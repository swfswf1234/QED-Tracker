# 手动知识导入设计

状态：Draft
任务类型：B
最后更新：2026-09-01
需求方：QED-Tracker（QED-050 双轨设计）
目标项目：QED-Tracker
评审方：用户

## 背景

QED-050 设计了手动+自动双轨知识获取：
- **自动轨**：LLM 探索管线（详见 [exploration-pipeline.md](2026-09-exploration-pipeline.md)）
- **手动轨**：人工整理 JSON 后通过 API/CLI 导入，跳过 LLM 直接写库

手动轨适用于：已有标准答案知识目录的领域（如 math-advanced）、人工整理的课程体系、外部 PDF 直接导入。

## 当前实现

### 三种导入模式

| 模式 | API 端点 | CLI 命令 | 写入表 | 来源标记 |
|---|---|---|---|---|
| 领域 JSON 导入 | `POST /domains/import` | `domains import <json>` | qed_domain + qed_course | source=manual |
| 课程 JSON 导入 | `POST /courses/{id}/knowledge` | `knowledge import <json>` | qt_knowledge + qt_books | source=manual |
| 书籍 PDF 导入 | `POST /books/{id}/import` | `books import <id> <path>` | qt_books + qt_sources | channel=local_import |

### Schema 契约

#### 领域 JSON（manual@v1）

```json
{
  "name": "数学（高等数学）",
  "description": "...",
  "stages": ["基础", "主干", "分支", "前沿"],
  "classic_tracks": [{"name": "分析学", "summary": "...", "kind": "main"}],
  "courses": [
    {
      "slug": "mathematical_analysis",
      "name": "数学分析",
      "track": "分析学",
      "stage": "基础",
      "prerequisites": [],
      "description": "..."
    }
  ]
}
```

代码位置：`application/knowledge_import.py` validate_domain
测试：`tests/test_knowledge_import.py`（validator + API 契约 + docs 合规）

#### 课程 JSON（course-knowledge/manual@v1）

```json
{
  "tutorials": [
    {
      "set_no": "1",
      "set_name": "菲赫金哥尔茨《微积分学教程》+ 吉米多维奇习题集",
      "textbook": {"title": "...", "roles": ["textbook"], "...": "..."},
      "exercise": {"title": "...", "roles": ["exercises"], "...": "..."},
      "target_path": "math-advanced/01_math_analysis/textbook_abc123.pdf"
    }
  ]
}
```

target_path 为期望磁盘路径（不含 sha 后缀），落盘时自动追加 `_<sha8>`。

#### 书籍 PDF 导入

请求体：`{file_path: "...", target_path?: "..."}`
流程：inspect_pdf（magic + pages）→ sha256 去重 → atomic move to raw/ → complete_download → add_source(channel=local_import)

代码位置：`api/main.py` POST /books/{book_id}/import（line 770）
测试：`tests/test_knowledge_import.py`（6 用例）

### 写入语义

| 行为 | 说明 | 代码位置 |
|---|---|---|
| 导入即确认 | 手动导入的教程自动置为 confirmed 状态，不走 LLM 审阅 | `cli.py` line 686 |
| exploration_stage=已完成 | 领域导入跳过探索流程，直接标记完成（D8） | `api/main.py` POST /domains/import |
| G2 修复 | complete_knowledge 全教程 completed 时回写 qed_course.exploration_stage=已完成 | `db/knowledge_repository.py` line 590 |

### 知识目录

```
docs/knowledge/
├── math-advanced.json          # 领域 JSON（12 门课程，四档 + kind）
├── math-advanced/              # 课程 JSON
│   ├── 01_math_analysis.json   # 含 target_path
│   ├── ...
└── computer-science.json       # 领域 JSON（5 门课程）
```

合规测试：`test_knowledge_import.py::test_knowledge_docs_conforms`、`test_knowledge_docs_computer_science_conforms`

### 校验逻辑

- validate_domain：参数化校验器，检查 name/description/stages/classic_tracks/courses 结构
- A2 source 扩展：source 字段接受 "manual" 值，roles 强制包含 textbook
- slug vs course_id 映射：当前 math-advanced.json 使用 slug（如 mathematical_analysis），catalog 使用 course_id（如 01_math_analysis），**O1 待裁决**

## 优化目标

| 优化项 | 目标 | 关联任务 |
|---|---|---|
| 三种导入全链路测试 | 领域/课程/书籍导入各场景覆盖 | QED-050-C |
| schema 契约冻结 | manual@v1 + course-knowledge/manual@v1 最终确定 | QED-050-C |
| slug/course_id 映射解决 | O1 待裁决项关闭 | QED-050-C |
| G2 回写验证 | complete_knowledge 回写逻辑端到端验证 | QED-050-C |

## 测试覆盖

| 测试文件 | 覆盖内容 |
|---|---|
| `test_knowledge_import.py` | validator + API 契约 + docs 合规 + G2 回写 + source/manual 3 用例 + import 6 用例 |
| `test_cli_knowledge_import.py` | CLI 链路（domains import / knowledge import / books import） |

## 关联文档

| 文档 | 关系 |
|---|---|
| [knowledge-dual-flow.md](2026-08-knowledge-dual-flow.md) | 双轨设计原始计划（M1-M7 已完成） |
| [exploration-pipeline.md](2026-09-exploration-pipeline.md) | 探索管线（手动导入的替代路径） |
| [download-registration.md](2026-09-download-registration.md) | 下载登记（书籍导入后的下游流程） |
| `design/acquisition-and-inventory.md` | 资源获取与库存（Accepted） |
| `design/tutorial-naming.md` | 教程命名规范（Accepted） |

## 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-09-01 | 初始创建 | 从 knowledge-dual-flow 整合，M1-M7 已完成 |
