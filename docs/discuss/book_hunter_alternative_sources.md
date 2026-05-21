# 📌 教材缺失源替代方案讨论

> **状态**: 方案 B 已实现（Z-Library 下载器），方案 A/C 待执行
> **关联**: 见 `docs/knowledge_base/inventory.md` 缺失清单，对应 T-201
> **编写**: 2026-05-17 | **更新**: 2026-05-21

## 现状

LibGen 搜索可达（需代理 7897），但下载服务器连接仍失败。已实现 Z-Library fallback 下载器 (`app/tools/zlib_downloader.py`)。

缺失清单（含课程 11-13 概率论方向）共 32 本教材：

| 分类 | 涉及书目 | 数量 | 问题 |
|------|---------|------|------|
| LibGen 下载失败 | Stein RA/CA, Evans PDE, 泛函学习指导 等 | ~4 | 下载服务器不通 |
| Z-Library 覆盖 | 中文教材 + 概率论英文教材 | 全部 | 待测试可达性 |
| 英文误匹配 | Stein, Evans 同名不同作者 | 3 | 需精确搜索或手动选择 |
| 概率论 10 本 | Durrett, Billingsley, Vershynin 等 | 10 | 新增课程，首次采集 |

## 方案 A：仅依赖 LibGen（现有路线）

**当前**: LibGen 搜索可达但下载不通，需修复代理/VPN 后重试。

## 方案 B：Z-Library 备用下载器 ✅ 已实现

> `app/tools/zlib_downloader.py` 于 2026-05-21 创建，接口与 LibGenDownloader 对齐。
> 已整合进 `app/collectors/textbook_hunter.py` 的 fallback 链：
> LibGen → Anna's Archive → Z-Library

**优点**: 中文数学教材齐全，PDF 质量好
**风险**: 域名频繁变更，需维护可达性检测（当前通过 `singlelogin.re` 访问）

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
Step 1 (P0): 配置代理/VPN → 测试 LibGen + Z-Library 可达性
  ├─ 测试 Z-Library: python -c "from app.tools.zlib_downloader import ZlibDownloader; print(ZlibDownloader().check_reachable())"
  └─ 测试 LibGen:   python scripts/hunt_textbooks.py --auto

Step 2 (P1): If Z-Library 可达 → 首次全量搜索 + 下载
  └─ 优先: 熊金城、丁同仁、张恭庆、冯克勤（LibGen 无中文源）

Step 3 (P2): 剩余缺口手动处理
  └─ 方案 C 按需执行
```

## 待办

- [ ] 配置代理后测试 Z-Library 可达性 (`check_reachable()`)
- [ ] 配置代理后测试 LibGen 下载恢复
- [ ] 重跑全量检索并记录结果
- [x] 实现 Z-Library 下载器 (`app/tools/zlib_downloader.py`)
- [x] 整合进 TextbookHunter 的 fallback 链
- [x] 扩展 math_qe.py 加入课程 11-13 概率论方向
