# 教程命名规范设计（tutorial-naming）

设计状态：Accepted
实现状态：Implemented
最后更新：2026-08-20
需求方：QED-Engine（根仓库 REQ-041「教程命名规范」，设计依据根仓库
[downloads-manage-redesign.md](../../../docs/design/downloads-manage-redesign.md) §2.3 用户裁决）
关联代码：`src/qed_tracker/db/knowledge_repository.py`（`tutorial_name` 命名函数）、
`src/qed_tracker/application/migrate_knowledge.py`（存量迁移命名 + 先查后建幂等）、
`src/qed_tracker/cli.py`（mainline new/review 默认命名与决定引用）
关联测试：`tests/test_migrate_knowledge.py`、`tests/test_main_line_cli.py`、
`tests/test_knowledge_api.py`
关联 ADR：无新增（沿用 [ADR 0001](../adr/0001-tracker-service-architecture.md)）

> **决策登记（2026-08-20 评审定案，QED-036 实现完成）**：
> 1. **方案 A**：`textbook_ref` 扩展为 `{title, version, authors}`，命名规则成为纯函数
>    `tutorial_name(set_no, title, authors)`（只依赖知识行自身，draft 期即可生成规范名）；
> 2. `mainline new` 增 `--set-no`（有则规范名，否则保持原始 title）；`mainline review` 增
>    `--title/--author`（缺省从规范名剥离「教程{set_no}：」前缀与（作者）后缀回退）；
> 3. migrate 改名后幂等键兼容：按 `(course, kind, set_no)` 先查后建（knowledge_id 含 name，
>    旧库重放不产生重复行），存量改名由一次性数据修正脚本负责（migrate 不覆盖 name）。

> **决策登记**：2026-08-18 根仓库用户裁决（ARCH-015 前端重构 D5）：教程命名由 QED-Tracker
> 数据侧统一，前端原样展示；name 为空时前端兜底「教程{set_no}」（前端已实现）。本设计只定
> 数据侧命名规范与落库改动，不涉及前端展示逻辑。

## 背景与目的

根仓库前端「文档下载管理」左树第四层为教程叶子，需要稳定、可读的教程显示名。当前
`qt_knowledge.name` 命名不统一：

1. **存量迁移**（`migrate_knowledge.py`）生成 `{title} 套{set_no}`（如「数学分析 套1」），
   书名直接拼接，无作者，格式与「套」语义混排；
2. **新建知识行**（`cli.py` 的 mainline new）直接 `name=args.title`，未按套规范生成；
3. `textbook_ref` 决定引用仅存 `{title, version}`，**无作者字段**，「书名（作者）」无现成来源。

根仓库 REQ-041 要求教程显示名统一为「教程N：书名（作者）」；en 套为「教程en：书名（作者）」。

## 命名规范（目标态）

对 `kind=tutorial` 的知识行：

| set_no | 命名格式 | 示例 |
| --- | --- | --- |
| "1"~"4"（中文套） | `教程{set_no}：{书名}（{作者}）` | `教程1：数学分析（Rudin）` |
| "en"（英文对照套） | `教程en：{书名}（{作者}）` | `教程en：Principles of Mathematical Analysis（Rudin）` |
| ''（空，异常/资料行） | `教程：{书名}（{作者}）` | 兜底，不鼓励出现 |

对 `kind=other_material`（课程延展资料归类）：**不加「教程N」前缀**，保持归类名
（如 `01-数学分析-延展资料`），本设计不改变其命名规则。

- 书名/作者取自**教材决定引用**（`textbook_ref`）或该套教材书行；无作者信息时省略
  （作者部分），退化为 `教程{set_no}：{书名}`。
- `name` 列仍允许人工覆盖（如经用户裁决改名），规范只约束默认生成路径。

## 决策点：书名/作者来源

`textbook_ref` 当前为 `{title, version}`（无作者）。实现前需在评审中选定：

- **方案 A（推荐）**：`textbook_ref` 扩展为 `{title, version, authors}`——决定引用补
  `authors`（list[str]），命名取 `textbook_ref.title` + `textbook_ref.authors`。语义集中，
  知识行自含命名所需信息；需同步 `database-schema.md` 决定引用说明与迁移时回填 authors。
- **方案 B**：命名时从该套**教材书行**（`qt_books` 中 `roles` 含 textbook 的首行）聚合
  `title` + `authors`。不改决定引用结构，但命名依赖书行存在性（draft 期书行可能未定）。
- **方案 C**：仅 `教程{set_no}：{书名}`，不显示作者。实现最简，但不符合根仓库裁决的
  「书名（作者）」格式。

推荐 **方案 A**：决定引用补齐 `authors` 后，命名规则成为纯函数（只依赖知识行自身），
draft 期即可生成规范名；存量 01 数学分析 3 行已有教材书行 authors 可回填。

## 改动范围

1. **命名默认值生成**：
   - `src/qed_tracker/application/migrate_knowledge.py`（migrate 循环内 name 生成，约 223 行）
     改为 `教程{set_no}：{书名}（{作者}）`（方案 A 下 book 创建后回填 textbook_ref.authors；
     存量重放时已有书行可读取）。
   - `src/qed_tracker/cli.py`（mainline new 新建知识行，约 697 行）name 默认值：有 set_no 时
     按规范生成，否则保持 title（draft 期命名，人工可在 review 时改）。
2. **textbook_ref 结构**（方案 A）：`database-schema.md` 决定引用说明补充 authors；
   存量 01 数学分析 3 行（kn_23d99d87728255e2328547a468396b23 / kn_b8e1576c05b7ac14fc3638fa2d1693c5 /
   kn_ad4d78ac7cd65bc0116fad84a5e5e77a）教材决定引用回填 authors，并同步将 `name`
   改为规范格式（一次性数据修正，`completed` 状态行仅改 name/textbook_ref，不动状态机）。
3. **文档白名单同步**：`tests/test_documentation.py` 的 `REQUIRED_CURRENT_DOCS` 与
   `DESIGN_DOCS` 加入本设计文档（新增设计文档必须登记，由 QED-Tracker 执行侧提交时同步）。

## 验证与回执（已完成）

- `tests/test_migrate_knowledge.py`（12 用例）断言存量迁移命名符合规范格式 + textbook_ref 回填
  authors + 先查后建幂等复用；`tests/test_main_line_cli.py` 断言 mainline new `--set-no` 规范名
  与 review `--title/--author` 决定引用；`tests/test_knowledge_api.py` 断言规范名经 API 透出。
- 真实 MySQL 冒烟（2026-08-20）：01 数学分析 3 行 `name` 修正为
  `教程1：数学分析原理（Rudin）`、`教程2：微积分学教程（菲赫金哥尔茨）`、
  `教程3：数学分析（陈纪修）`（套 3 书行 title 已含「（陈纪修）」由命名函数去重）；
  8901 `GET /knowledge` 返回新 name，status 保持 completed；证据归档
  [docs/history/qed-036-tutorial-naming/](../history/qed-036-tutorial-naming/)。
- 回执根仓库 REQ-041（提交号 + 测试输出）已整理，待写入；根仓库前端左树教程叶子联调验收。