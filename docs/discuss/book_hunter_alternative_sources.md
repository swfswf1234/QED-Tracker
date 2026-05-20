# 📌 教材缺失源替代方案讨论

> **状态**: 讨论中
> **关联**: 见 `docs/knowledge_base/inventory.md` 缺失清单，对应 T-201
> **编写**: 2026-05-17

## 现状

LibGen 7 镜像全部不可达（当前网络无代理/VPN），已成功下载的 17 本 PDF 保持在 v0.1 状态。

缺失 11 本教材分三类场景：

| 分类 | 涉及书目 | 数量 | 问题 |
|------|---------|------|------|
| LibGen 不可达 | 全部依赖 LibGen 的书籍 | 全部 | 网络/代理问题 |
| 中文教材无源 | 熊金城、丁同仁、张恭庆、冯克勤、方企勤、Evans 中译本 | 6 | LibGen 无这些中文源 |
| 英文误匹配 | Stein *Real Analysis*, Stein *Complex Analysis*, Evans *PDE* | 3 | 同书名不同作者，置信度低 |
| 下载中断 | 泛函分析学习指导 | 1 | 网络中断，需续传 |

## 方案 A：仅依赖 LibGen（当前路线）

直接解决代理问题后重试全量。

**步骤**:

1. 确保 `setting.ini` 中 `[Proxy]` 段配置正确
2. 确认 WSL 网络模式可连通（WSL2 NAT 模式需额外配置端口转发）
3. 运行 `python scripts/hunt_textbooks.py --all`
4. 对 Stein/Evans 等误匹配结果，在交互模式下手动选择正确版本

**已知限制**:
- 中文教材（熊金城、丁同仁、张恭庆等）LibGen 大概率无源
- Stein/Evans 英文版需要更精确的搜索词或手动选择

## 方案 B：Z-Library 备用下载器

Z-Library 中文教材覆盖率高于 LibGen，可作为主要补充源。

**方案要点**:
- `app/tools/zlib_downloader.py` — search + download 接口，与 LibGenDownloader 对齐
- 通过 `singlelogin.re` 域名访问
- 整合进 TextbookHunter 的 fallback 链路：LibGen → Z-Library → 手动

**优点**: 中文数学教材齐全，PDF 质量好
**风险**: 域名频繁变更，需维护可达性检测

## 方案 C：中文专用源

针对纯中文教材，定向爬取以下来源：

| 来源 | 覆盖范围 | 可行性 |
|------|---------|--------|
| 超星/读秀 | 高校教材 PDF，需机构权限 | ⚠️ 部分受限 |
| 全国图书馆参考咨询联盟 | 可试读，下载受限 | ⚠️ 有水印 |
| 百度网盘资源 | 非结构化，需采集 | ⚠️ 稳定差 |
| 高校个人主页 | 部分教授放自家教材 | ✅ 可用但零散 |
| 购买扫描 | ISBN 确认后购买电子版 | ✅ 最可靠但需成本 |

## 建议执行路线

```
Phase 1 (P0): 修复网络 → LibGen 全量重试
  └─ 结果: 评估哪些已解决、哪些仍需补充

Phase 2 (P1): 根据 Phase 1 结果决策
  ├─ 若中文教材仍缺失 → 方案 B (Z-Library)
  └─ 若英文误匹配仍存在 → 人工手动选择 + 更新搜索词

Phase 3 (P2): 剩余缺口处理
  └─ 方案 C (中文专用源按需执行)
```

## 待办

- [ ] 验证代理/VPN 配置后 LibGen 是否可达
- [ ] 重跑 LibGen 全量检索并记录结果
- [ ] 更新 `docs/knowledge_base/inventory.md` 反映新状态
- [ ] 如决定引入 Z-Library，创建 `app/tools/zlib_downloader.py`



