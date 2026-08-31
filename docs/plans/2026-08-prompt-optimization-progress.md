# QED-043 进度追踪：prompt 优化模块

状态：Active
最后更新：2026-08-28
> 设计文档：[2026-08-prompt-optimization.md](2026-08-prompt-optimization.md)（Accepted）
> 需求方：QED-Engine REQ-060
> 模板注册：`src/qed_tracker/prompt_lab/templates.py`（版本化，git 即历史）

## 当前状态（2026-08-28）

| 维度 | 状态 |
|------|------|
| 领域管线 | v2/v4/v4 全链验证通过（calls 100~102），13 门输出，基线冻结 |
| 课程管线 | tutorials@v1 实现完成；**标准答案范本定稿**（[course-tutorials-math-golden.json](../knowledge/course-tutorials-math-golden.json)，三课程 7 套，守护测试 4 用例） |
| 数据根 | QED_DATA_ROOT=D:\coding\QED-Engine\dataset 确认；旧布局/失效清单/仓内残留已清理（见 08-28 台账） |
| 门禁 | **343 passed + 3 skipped + ruff clean** |
| 阻塞 | 无 |

### 待办

- [ ] tutorials 双跑真实评估（direct + ref_text=tmp 探索笔记，× 三课程，对照 golden）
- [ ] tutorials@v2：放宽「至少一套须含独立习题集」全局强制（11 号课 exercise_count=0，见 golden meta.contract_notes）
- [ ] 数据库播种（domain math + 三基石课）+ golden 经 A2 采纳落 draft（QED-026/QED-047 链路）
- [ ] 下载流程梳理 plans/ 文档 + 成功率/准确率分析 + 验收标准讨论（QED-026 收尾）
- [ ] Phase B 端点组（/api/v1/prompt-explores 课程侧 + CLI）
- [ ] REQ-060 根仓库改造回执接收（提交号）

---

## 进度日志

### 2026-08-28：课程教材层标准答案范本定稿（QED-026/QED-043 轮）

**golden 定稿**：`docs/guides/course-tutorials-math-golden.json`（数学分析 3 套 / 高等代数 2 套 / 概率论与数理统计 2 套，共 7 套，tutorials@v1 契约格式）。守护测试 `tests/test_course_tutorials_golden.py` 4 用例（01/02 全契约校验通过；11 逐条目校验 + exercise_count=0 已知偏离显式断言）。

**用户裁决**（本轮）：golden 放 docs/guides 单文件；只播种 3 门基石课（catalog 对齐 course_id）；A2 采纳到 draft 即止；评估 direct + ref_text 双跑；数学分析甲方案（Stewart/Apostol/Rudin+吉米多维奇），陈纪修留 catalog 套三不进 golden；高等代数以 Strang LAA 中译为准 + 苏联《线性代数习题集》挂 Axler 套 + 课程名「高等代数」（别名线性代数）；概率论只留 Blitzstein/Ross 两套（茆诗松/Casella 缓议）；catalog 11 目标（Durrett/Billingsley 测度论概率）留待未来「高等概率论」扩展课。

**书目核查证据**（豆瓣，2026-08-28）：《斯图尔特微积分（第九版·上）》人民邮电出版社图灵数学经典 2025（ISBN 9787115667250，原作 Calculus: Early Transcendentals）；《斯特朗线性代数》图灵数学经典 2025（ISBN 9787115676849，**原作名 Linear Algebra and Its Applications**——与 Lay 同名书区分，也非 Introduction to Linear Algebra）；《概率导论（第2版·修订版）》图灵数学经典（Blitzstein 中译正式书名为「概率导论」）；《线性代数应该这样学（第4版）》图灵数学经典。

**契约发现**：①书名强制中文（CJK 校验）→ en 英文对照套与纯英文题解（Axler solutions/Grimmett 1000/Casella solutions）无法表达，留 catalog 侧；②11 号课两套均教材自带习题 → exercise_count=0 违反 v1「至少一套须含独立习题集」→ **tutorials@v2 需放宽该全局强制**（保留单套规则），A2 采纳端点轻校验不受影响。

**数据根清理台账**（QED_DATA_ROOT=D:\coding\QED-Engine\dataset 确认后执行，均先安全断言再删）：
- ① `dataset\tmp\exploration\`（4 个探索 txt 冗余副本，正本在仓库 tmp/）→ 删除
- ② `dataset\qed-tracker\raw\books\`（ARCH-019 前旧布局，空目录树）→ 删除
- ③ `dataset\qed-tracker\meta\resources\` 12 条失效清单记录（全部指向旧路径 raw/books/math-qe/...，文件已迁 raw/math/01_math_analysis/）→ 删除 + `inventory scan` 原地重登记（**12 registered / 0 errors**，`inventory verify` 12/12 ok，sha256 与旧记录一致证明文件完好）
- ④ 仓内 `QED-Tracker\dataset\`（历史误运行残留数据根：serve-8901 日志 + 同哈希 meta 副本 29 个文件，无 PDF，被 .gitignore 掩盖）→ 删除

### 2026-08-26 晚：课程管线重新设计

用户裁决砍 tree 改**单步 tutorials**（P7 修订：课程已有介绍，一个 prompt 即出「教材+习题集」成套方案）。

- `course-explore/tutorials@v1` 模板注册（中文书名优先 + original_title 承载原版 + roles 对齐 qt_books + position 三档 beginner/comprehensive/advanced + 六要素 intro 100~300 字 + 同源可空 + 主教材不重复）
- `priors.py` tutorials 步键集（textbook_preference 注入）
- `CoursePipeline` 单步编排（enrich proposal_id=pp_*）
- 守护测试 20 条（模板全边界 + payload 注入断言 + 坏 JSON 修复 + 预算耗尽）
- 真实评估**待执行**——评估脚本保留

### 2026-08-26 探索轮全链验证

v2/v4/v4 全链验证通过（calls 100~102，qwen3.7-plus）：

- domain@v2 五项文案落地、courses@v4 数量区间入参 + university_basis 可空、path@v4 summary 依据判断
- priors 四主线对齐 + 分步裁剪注入
- pipeline scope_hint 贯穿 + tracks 全量 + count_range
- 输出 13 门（10 slug 命中 + 2 漂移 + 1 extra）；DAG 5/10 一致
- classic_tracks 漂移（三主线而非 golden 四主线），需后续优化
- 知识文档 `docs/knowledge/math-advanced.json`（12 门 + 17 扩展 + DAG；2026-08-29 迁入 knowledge/ 为正本，旧副本 plans/guides 已删除）已定稿迁移

### 2026-08-26 Round 1 重跑

用户裁决探索管线切换 qwen3.7-plus（P15a），8901 重启后高等数学批重跑成功：

- calls 97~99 全 success：domain 39.9s / courses 95.5s（旧 60s 必死 = REQ-061 同步实证）/ path 47.3s
- 13 门课 19 边
- 定性对比登记 baseline §6-8——ODE/PDE 自发入选、slug/tier/课名跨轮漂移显著
- 优化轮评估须同模型同日多轮取交集

### 2026-08-26 REQ-063 + Round 1 启动

- 根 .env 补 QED_LLM_TIMEOUT=300
- REQ-063 按方案一执行完毕（删 4 键 GATEWAY_URL/DB_PORT/DB_NAME/DB_USER——内置默认同值；保 API_KEY/QED_DB_PASSWORD 独立运行底线 + DB_HOST/DATA_ROOT 清单外完整性键 + API_SELECT/MODEL/PORT 覆盖私有键）
- operations.md 与 model-mode-config.md 已同步，load_settings 全链验证 PASS
- templates.py 两处陈旧 courses@v2 注释修正（零行为变化）
- 8901 已重启加载新配置链（health ok）

### 2026-08-26 Phase B0 参照跑

采纳 Engine 侧诊断并本侧复核（P15）：

- domain@v1 单步三模型参照全通过（calls 91~93：qwen3.8-max 39.8s / qwen3.7-plus 35.0s / qwen3.8-27b 28.3s 均 valid=true）
- 课程检索优化后置（课程管线未重新规划）
- REQ-061 的 QED_LLM_TIMEOUT 键映射同步进本仓（默认 300s，TDD：config 测试先行），基线 §7 超时预算开放问题就此裁决关闭

### 2026-08-26 REQ-060 落地 + 需求方反馈

- REQ-060 用户确认落地：qed_llm_calls 扩展列 task/step/review_status/review_note + GET 过滤 + PATCH review 端点 + web-ui 控制台审核页
- 按 P14 取消 tmp/prompt-eval/ 人工审阅导出通道并删除目录（审阅一律走共享表 + 根仓库前端）
- prompt 优化范围裁决：仅 prompt_lab 体系内（课程侧 = 待新建 tree/tutorials 两步管线，QED-041 advisor 不迁移，P9 维持）

**需求方反馈（根仓库登记）**：

1. curriculum 探索 prompt 需约束课程命名——domain_name=数学 时 LLM 自创「高级数学分析」，建议模板输出规范课名或提供候选枚举
2. §8 缺陷两处：`GET /courses/{domain_id}` 被 `{course_id}` 路由遮蔽返回 405；`PATCH /courses/{id}` 对 prerequisites 字段不生效
3. **adopt 落库预填缺失**：课程层探索采纳生成的 draft qt_knowledge 行 textbook_ref/exercise_ref/textbook_intro/exercise_intro 全空（2026-08-25 细化字段约定：set_name=中文教程名+作者；textbook.title/exercise.title=中文书名不带作者；intro 含英文原名+来源+定位+理由；同源可空）
4. 模板约束教材/习题集名称**中文优先**输出
5. **课程简介自动生成**：curriculum 探索时为每门课程产出一句中文简介，落库到 course.note 字段

### 2026-08-25 基线冻结

v3 三步管线首轮全链路真实结果冻结为优化基线：

- qed_llm_calls 073~079：高等数学 12 门 + 计算机科学与技术 16 门双批 ready
- 名称确认流实战——LLM 建议「数学」、人工裁决保留原名后 confirm_name_override 重跑通过
- 基线表、差距观察与开放问题见 [领域探索 prompt 优化基线](2026-08-prompt-explore-baseline.md)

### 2026-08-24 Phase 0+A+B0 完成

- 设计 Accepted（决策 P1~P11 用户裁决），REQ-060 已登记
- Phase 0：_record_call 修复 + 5 调用点补编号
- Phase A：模板注册表学科中立化 + 领域 4 步管线 + dry-run 评估端点
- Phase B0：345 passed + 3 skipped + ruff clean
- 待用户真实冒烟评估 → Phase B 正式流程
