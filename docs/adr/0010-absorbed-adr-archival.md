# ADR 0010：已承接 ADR 的归档机制（新增 Absorbed 状态）

状态：Accepted
日期：2026-09-21
最后更新：2026-09-21
领域：工程治理
决策阶段：v1.0
取代：—
被取代：—

## 背景

`docs/adr/` 已积累 9 份 ADR。其中多份工程治理类决策（0002/0003/0004/0005/0007/0008/0009）
的机制内容已完全并入 `doc-governance.md`、数据库设计文档、`design/index.md` 等稳定文档，
ADR 本体只剩「历史理由」。但 [ADR 治理规范](../standards/adr-governance.md) 的归档通道只有
`Rejected` 与 `Superseded`——「决策未被推翻、仅内容已被承接」的 ADR 没有去处，活跃区持续
膨胀，稀释「当前生效的长期约束」这一信号。2026-09-21 主线梳理轮用户裁决引入承接归档机制。

## 决定

1. **新增 `Absorbed` 状态**：ADR 状态枚举由 `Proposed / Accepted / Rejected / Superseded`
   扩为 `Proposed / Accepted / Rejected / Superseded / Absorbed`。`Absorbed` 语义：决策未
   被推翻，但其约束内容已由稳定文档（standards/architecture/design）完整承接，ADR 仅保留
   决策理由的历史价值。
2. **归档路径**：`Absorbed` ADR 移入 `docs/history/adr/`（与 Rejected/Superseded 同目录），
   文件名不变，编号永不复用（沿 [ADR 0009](../history/adr/0009-closed-plan-archival.md) 的
   归档不删除口径）。
3. **判定与登记**：转 `Absorbed` 必须经用户确认，且逐条决定均有明确承接落点；移动时状态改
   `Absorbed`、补 `承接落点` 元数据行与承接日期，正文决定内容不改写（沿用「Accepted ADR
   正文不得静默改写」，允许修复链接与补充反向关系）。仍具活约束而承接不完整者不得以本机制
   归档（首例执行保留 0001 服务化契约与 0006 数据库策略于 `docs/adr/`）。
4. **登记处**：`docs/adr/index.md` 单列「已承接归档」表链接至 `../history/adr/`；
   `docs/history/index.md` 同步登记去处。
5. **入站链接义务**：当前文档（history 豁免）指向被归档 ADR 的链接改指 `history/adr/` 路径，
   由 `tests/test_documentation.py` 链接守护兜底。

## 后果

- ADR 活跃区只保留仍在约束实现且理由需常反查的决定；治理类一次性裁决有正式去处。
- 版本末期整理新增一个审视项：Accepted ADR 是否已被稳定文档完整承接（并入
  [文档治理规范](../standards/doc-governance.md)「版本末期文档整理」检查清单第 1 条的语义，
  不改条目文字）。
- 首批适用：0002/0003/0004/0005/0007/0008/0009 归档，0001/0006 保留。

## 关联

- 关联标准：[ADR 治理规范](../standards/adr-governance.md)（状态枚举与归档路径本轮同步）、
  [文档治理规范](../standards/doc-governance.md)（归档与删除节同步）
- 关联 ADR：[ADR 0009](../history/adr/0009-closed-plan-archival.md)（关闭计划归档默认
  Retain 的同类口径）、[ADR 0002](../history/adr/0002-version-cleanup-governance.md)～
  [ADR 0008](../history/adr/0008-design-doc-scope-reshuffle.md)（首批归档对象）
- 关联测试：`tests/test_documentation.py`（入口白名单与链接守护）
