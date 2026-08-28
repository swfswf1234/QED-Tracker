# QED-043 进度追踪：prompt 优化模块

状态：Active
最后更新：2026-08-27
> 设计文档：[2026-08-prompt-optimization.md](2026-08-prompt-optimization.md)（Accepted）
> 需求方：QED-Engine REQ-060
> 模板注册：`src/qed_tracker/prompt_lab/templates.py`（版本化，git 即历史）

## 当前状态（2026-08-26 晚）

| 维度 | 状态 |
|------|------|
| 领域管线 | v2/v4/v4 全链验证通过（calls 100~102），13 门输出，基线冻结 |
| 课程管线 | `course-explore/tutorials@v1` 实现完成（砍 tree，单步 tutorials） |
| 门禁 | **378 passed + 3 skipped + ruff clean** |
| 阻塞 | 无 |

### 待办

- [ ] 执行 `tmp/run_course_tutorials.py` 对数学分析执行 tutorials@v1 真实评估
- [ ] Phase B 端点组（/api/v1/prompt-explores 课程侧 + CLI）
- [ ] DAG 约束增强 + slug 强制规范 + tracks_hint 文案优化
- [ ] REQ-060 根仓库改造回执接收（提交号）

---

## 进度日志

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
- 知识文档 `docs/guides/domain-math-advanced.json`（12 门 + 17 扩展 + DAG）已定稿迁移

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
