# ADR 0011：仓库产物三类落位（logs / tmp / QED_DATA_ROOT）

状态：Accepted
日期：2026-09-30
最后更新：2026-09-30
领域：工程治理
决策阶段：v1.0
取代：—
被取代：—

## 背景

三类产物长期错位：`logs/` 本是被服务生命周期脚本与运维文档功能引用的运行产物目录
（pid / mode / 两个 `.log`），但 QED-067/072/073/074 各计划把探针脚本与捕获输出留在
`logs/`，使其混入十余件开发杂物；仓库根 `tmp/` 长期空置，一次性文件散落在根目录与
`logs/`，并曾直接污染完成门禁（QED-074 计划 2.4 实况：根目录散件致 `ruff check .` 报
18 处）；重要过程数据（用户输入件、真实模型试运行产物、回填举证）无落位口径，混放于
仓库 `tmp/`。跨项目契约已由根仓库定义 `QED_DATA_ROOT` 顶层白名单与 `tmp/<项目>/` 分桶
（dataset-conventions，raw 不可变、tmp→raw 原子落盘），本仓库一直未承接为可执行规则。

## 决定

- **D-1 `logs/`＝服务运行产物专用**：只存放 `scripts/qed_tracker_service.py` 与运维文档
  功能引用的文件（`qed-tracker.pid`、`qed-tracker-mode`、`qed-tracker-serve.log`、
  `qed-tracker.log` 及其后续等价件）。开发临时文件与取证文件禁止入内。
- **D-2 `tmp/`＝仓库开发临时区**：探针脚本、捕获输出、一次性编辑脚本一律落此（目录已
  gitignore，且不污染 `ruff`/pytest 收集面）。`tmp/` 不得充当长期证据库：证据的结论与
  索引必须写入 `docs/plans/` 对应计划，原件视为易逝、可弃。
- **D-3 重要过程数据→`QED_DATA_ROOT`**：用户输入件、真实模型试运行产物、渠道评估回填
  举证等，按根仓库 dataset 契约落 `tmp/qed-tracker/` 分桶；被采纳内容按契约经 tmp→raw
  原子落盘，`raw/` 不可变。本仓库不复制根契约正文，只链接（见关联节）。
- **D-4 历史引用不改写**：`docs/history/` 与已关闭基线中「探针落 `logs/`」的既往记载保留
  当时结论；活跃计划的前瞻性措辞统一改 `tmp/` 并加当日注记。
- **D-5 存量清扫**：由 QED-075 W-6 执行清单承接——`logs/` 非运行产物经用户裁决直接删除
  （不可恢复已确认）；根目录散件收编 `tmp/`；`tmp/` 内用户数据件按 D-3 移交数据根。

## 后果

运行事实与开发杂物物理分离，`logs/` 恢复纯功能目录；完成门禁不再被散件连坐；过程数据
落位与根契约一致，跨项目回读入口统一。代价：清扫为不可逆删除（Git 无锚点），证据原件
仅存于计划摘要与 `qed_llm_calls` 留痕；后续任何新落位需求须修订本 ADR 而非各自约定。

## 关联

- [本地开发环境](../standards/local-dev.md)「开发产物落位」节（本决定的可执行规则，不复制理由）
- [服务管理设计](../design/service-management.md)「运行事实」节（`logs/` 专用口径）
- [文档治理规范](../standards/doc-governance.md)（plans/ 保存计划事实、tmp/ 不充当证据库的边界依据）
- 根仓库 `docs/design/dataset-conventions.md`（`QED_DATA_ROOT` 分桶与 raw 纪律，只链接不复制）
- [QED-075 治理轮计划](../history/baselines/2026-09-30-todo-governance-round.md)（W-5 承接本 ADR，W-6 承接 D-5）
