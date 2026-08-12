# 套标记字段设计：catalog target 增加 set_no（QED-024，承接根仓库 REQ-028）

设计状态：Draft（待用户评审）
实现状态：Not Started
最后更新：2026-08-12
关联代码：`src/qed_tracker/catalogs/math-qe.json`、`src/qed_tracker/models.py`（CatalogTarget）、
`src/qed_tracker/api/main.py`（catalogs 响应）
关联测试：`tests/`（catalog schema 相关测试，实现时补充）
关联 ADR：—
需求方：QED-Engine（根仓库 REQ-028；课程收集流程前端对齐契约，
见根仓库 `docs/design/course-acquisition-flow.md` 前端对齐契约第 1 条）
执行方：QED-Tracker
接口面：`GET /api/v1/catalogs/{id}` 响应中 target 对象新增可选字段 `set_no`（catalog JSON schema
版本 1 增列，非破坏性）
评审方：用户
验收标准：见下「成功标准」

## 背景

课程收集流程（根仓库 course-acquisition-flow.md）定义**一套 = 教材 + 配套习题集**（同作者/同系列
配套；英文原版对照单独计为英文套），每课程固定两套、可到三套、最多四套。前端 8903 需要按
「套」显示课程完成判定（≥2 套 approved 即完成）与进度文案「套数 x/2」。

当前 catalog target **没有结构化套字段**：仅 01 数学分析在 `note` 文本中带「套一/套二/套三」前缀，
其余课程无任何套信息，前端无法可靠推导套归属（作者集匹配对无作者习题集、多作者、中英对照等
场景不可靠）。

## 变更内容

1. `CatalogTarget` 增加可选字段 `set_no`（字符串，缺省 `""`）：
   - 取值约定：`"1"` / `"2"` / `"3"` / `"4"`（中文套，按目标属于第几套）与 `"en"`（英文原版
     对照套，单独计套）；无配套归属的目标留空（如独立补充资料 supplement）。
   - 同一课程内 `set_no` 相同的 target 属于同一套；一套必须含 ≥1 本 book 与 ≥1 本 exercise
     （supplement 不参与计套，可归属某套或留空）。
   - 示例：01 数学分析——套一 `01-rudin-zh`(book)/`01-demidovich`(exercise)/`01-feidinghui`
     (supplement) 均 `set_no="1"`；套二菲赫金哥尔茨三卷 + 谢惠民上下册 `set_no="2"`；
     套三陈纪修 v1/v2 + answers `set_no="3"`；`01-rudin-en`/`01-polya` 英文对照 `set_no="en"`。
2. `math-qe.json` 13 门课程 54 个 target 补齐 `set_no`（按定稿书单归属；无配套课程如实留空）。
3. `GET /api/v1/catalogs/{id}` 响应透出 `set_no`（asdict 已透出 dataclass 字段，确认契约测试）。
4. **不破坏性**：`set_no` 可选，旧客户端不受影响；不改变 evaluate/下载等既有行为。

## 成功标准

- `math-qe.json` 全部 target 含 `set_no`（无配套者留空），01 数学分析套归属与既有 note 一致。
- catalog API 响应含 `set_no` 字段；schema 契约测试更新。
- 回执根仓库 REQ-028（提交号 + 测试输出），根仓库前端两套判定联调验收（01 三套全 approved
  显示「已完成 +1」）。
