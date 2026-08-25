# 领域探索 prompt 优化基线（QED-043）

状态：Active（基线已冻结：后续模板/先验优化一律以本文件第 5 节为对照基准；真实对照口径待用户评估确定）
最后更新：2026-08-25
关联任务：todo [QED-043（长期任务）](../trackers/todo.md)；关联设计：[prompt 优化模块设计](2026-08-prompt-optimization.md)（P11/P12/P13）
数据来源：共享表 `qed_llm_calls` id 073~079（MySQL qed 库，qwen-plus，dry-run 模式）
参考文本：`<数据根>/tmp/exploration/高等数学探索.txt`（golden 参照，对照口径未定）

## 1. 目的与使用方式

记录 v3 三步管线（domain → courses → path）首轮**全链路成功**的真实结果，冻结为后续 prompt 优化的对照基线。
后续每轮优化按以下循环执行，并在本文件登记差异：

```
改 templates.py / priors.py → 模板 version+1 → dry-run 重跑（qed_llm_calls 新 call_id）
→ 与第 5 节基线对比 → 差距登记回第 6 节 → 用户审核裁决
```

「真实对照（高等数学领域 vs 参考文本）的近似度评判口径——课程覆盖集合、DAG 结构、主线命名各自占多少权重——
待用户下一步评估和确定」，在此之前第 6 节所有差距仅作候选线索，不构成修改依据。

## 2. 当前实现现状（2026-08-25 快照）

- **管线**：`DomainPipeline`（contract_version=`prompt-optimize-v3`），三步 domain/courses/path；
  describe 已并入 courses 的 summary 字段（60~200 字）。
- **模板注册表**：`src/qed_tracker/prompt_lab/templates.py` 当前版本 `domain-explore/domain@v1`、
  `domain-explore/courses@v3`、`domain-explore/path@v3`（模块 docstring 中"courses@v2"为陈旧描述，
  待下轮顺手修正）。
- **先验注入**：`src/qed_tracker/prompt_lab/priors.py` 仅注册「高等数学」：教材偏好 / 三主线提示 /
  国内命名惯例 / **三门基石锚点**（数学分析、高等代数、概率统计必须入选）/ level 默认 / QE 冲刺顶峰提示。
- **名称确认流（P12）**：domain 步 `name_check.valid=false` 或建议名不同且无人工确认时抛
  `NameConfirmationRequired` 提前结束；带 `confirm_name_override` 重跑则以该名贯穿全程。
- **评估模式（P11）**：`POST /api/v1/prompt-explores/dry-run` 同步执行，只落 qed_llm_calls，
  不写 qt_prompt_runs、不入队、不 apply。
- **跨步校验**：courses.track 必须逐字 ∈ classic_tracks；path.assignments 必须与课程清单完全一致。

## 3. 基线运行台账（qed_llm_calls 073~079）

### 高等数学批（74→75→76 生效；73 为确认流前半）

| id | 模板 | 耗时 | 说明 |
| --- | --- | --- | --- |
| 73 | domain@v1 | 12.6s | name_check.valid=false（建议改名"数学"）→ 抛 NameConfirmationRequired 中止 |
| 74 | domain@v1 | 8.5s | 用户裁决保留原名后 confirm_name_override="高等数学" 重跑，同名贯穿 |
| 75 | courses@v3 | 51.8s | 12 门课（含三门基石），贴近超时预算 |
| 76 | path@v3 | 8.6s | 12 门全覆盖，无环无自环 |

### 计算机科学与技术批（77→78→79，direct 无参考文本）

| id | 模板 | 耗时 | 说明 |
| --- | --- | --- | --- |
| 77 | domain@v1 | 7.2s | name_check.valid=true 直通（教育部正式专业名） |
| 78 | courses@v3 | 46.9s | 16 门课 |
| 79 | path@v3 | 9.1s | 全覆盖，四档分布 基础4/进阶8/核心2/冲刺2 |

背景：62~72 为当日调试轮（5 次 courses ReadTimeout，60s 预算不足）；45~48 为 v2 迭代历史轮；
49~58 为 v3 早轮。均不入基线。

## 4. domain@v1 基线输出要点（call 74）

- `name_check.valid=false`，reason：高等数学是工科公共课泛称；`suggested_name=数学`；**人工裁决保留原名**。
- final_name=高等数学；level=本科-硕士。
- classic_tracks 四条：分析学 / 代数学 / 概率与统计 / 几何与拓扑。
- entry_requirements：高中数学（含初等函数与解析几何）、逻辑推理与严格证明基础。
- description ≤200 字合规。

## 5. 高等数学课程×层级×先修基线表（call 75 + 76 合并视图）

| # | slug | 课程 | aliases | track | tier | prerequisites |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | mathematical_analysis | 数学分析 | 微积分；Analysis I & II | 分析学 | 基础 | — |
| 2 | advanced_algebra | 高等代数 | 线性代数；Abstract Linear Algebra | 代数学 | 基础 | — |
| 3 | probability_theory_and_mathematical_statistics | 概率论与数理统计 | 概率统计；Probability and Statistics | 概率与统计 | 基础 | — |
| 4 | point_set_topology | 点集拓扑学 | 一般拓扑学；Topology | 几何与拓扑 | 进阶 | 1, 2 |
| 5 | numerical_analysis | 数值分析 | Numerical Methods；Scientific Computing | （空=跨主线单列） | 进阶 | 1, 2 |
| 6 | real_analysis | 实变函数与泛函分析基础 | 实分析；Real Analysis | 分析学 | 核心 | 1, 4 |
| 7 | complex_analysis | 复变函数 | 复分析；Complex Analysis | 分析学 | 核心 | 1 |
| 8 | abstract_algebra | 抽象代数 | 近世代数；Modern Algebra | 代数学 | 核心 | 2 |
| 9 | differential_geometry | 微分几何 | 古典微分几何；Differential Geometry of Curves and Surfaces | 几何与拓扑 | 核心 | 1, 4 |
| 10 | stochastic_processes | 随机过程 | Stochastic Processes | 概率与统计 | 核心 | 3, 6 |
| 11 | functional_analysis | 泛函分析 | Functional Analysis | 分析学 | 冲刺 | 6, 7 |
| 12 | algebraic_topology | 代数拓扑 | Algebraic Topology | 几何与拓扑 | 冲刺 | 4, 8 |

每门课 summary 60~200 字（内容详见 qed_llm_calls call 75 response）；university_basis 以清华大学
课程代码为首条（如 00420011 数学分析 I/II/III），真实性未抽查。tier 分布：基础 3 / 进阶 2 / 核心 5 / 冲刺 2。

## 6. 与参考文本的差距观察（候选线索，非结论——待评估定口径）

1. **课程缺失**：常微分方程、偏微分方程（参考文本分析线主干）、测度论概率/高等概率论（研究生概率课）、
   凸优化、图论、组合数学、交换代数、同调代数均未入选；12 门 vs 参考文本约 16 门。
   三门基石锚点经 priors 强制后已稳定入选，但 anchor 之外的覆盖无约束。
2. **层级存疑**：泛函分析被排入「冲刺」（惯例为研究生基础/主干）；QE 顶峰以泛函+代数拓扑间接承担，
   无显式 capstone 表达。
3. **先修存疑**：随机过程未挂泛函前置（参考文本 FA→SP）；微分几何挂点集拓扑前置（古典微分几何通常
   数分+高代即可）；数值分析→进阶合理。
4. **课程重叠解释项**：「实变函数与泛函分析基础」（清华本科合并课）与「泛函分析」（研究生课）并存，
   符合国内课程设置但需在 apply 口径上明确是否视为两门。
5. **同输入不稳定**：call 73 与 74 输入完全相同，输出漂移（73 出现「本科-硕士-博士」层与
   「分析主线/代数主线…」命名；74 为「本科-硕士」与「分析学/代数学…」命名）。下游 track 逐字匹配
   依赖该输出，稳定性影响可比性。
6. **性能贴线**：courses@v3 成功耗时 47~52s，逼近 60s ReadTimeout（62~72 五次超时即此原因）；
   输出瘦身或超时调大二选一待裁决。
7. **university_basis 可信度**：清华课程代码未抽查；「多所顶尖大学共同开设」式兜底措辞本轮未出现，
   但历史轮出现过，需持续观察。

## 7. 开放问题（等下一步评估和确定）

- 真实对照口径：以参考文本为 golden 时，课程集合覆盖率 / DAG 边正确性 / 主线命名一致性如何量化？
- ODE/PDE 是否必须入选？若是，走 priors.anchor_courses 扩充还是 templates 层「各主线本科主干齐全」约束？
- 泛函分析 tier 是否纠偏为「核心」？
- 超时预算处理：调大 client timeout 还是压缩 courses 输出契约？
- 计算机批 tier 分布（进阶 8 门偏多、核心仅 2 门）是否符合预期，是否需要通用 tier 校准规则？

## 关联文档

- [prompt 优化模块设计](2026-08-prompt-optimization.md)（Accepted：P11 dry-run / P12 三步管线与确认流 / P13 先验注册表）
- [主链路设计](../design/main-line-curriculum.md)（math.json 14 门体系可作第二参照系）
