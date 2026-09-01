# QED-036 教程命名存量修正证据

状态：Current
最后更新：2026-08-20
任务：QED-036（跨项目，需求方 QED-Engine REQ-041「教程命名规范」）
设计：[教程命名规范设计](../../design/tutorial-naming.md)

## 修正内容

存量 01 数学分析 3 教程行（completed 态，**只改 `name` / `textbook_ref` 两列**，
不动状态机；`updated_by='qed036'`）按规范「教程{set_no}：书名（作者）」改名，
并回填决定引用 authors（书籍来源：roles 含 textbook 的首行，中文套优先 zh 语言书籍）。

| knowledge_id | set_no | before name | after name | textbook_ref |
| --- | --- | --- | --- | --- |
| kn_23d99d87728255e2328547a468396b23 | 1 | 数学分析原理（Rudin） 套1 | 教程1：数学分析原理（Rudin） | {title: 数学分析原理, authors: [Rudin], version: {}} |
| kn_b8e1576c05b7ac14fc3638fa2d1693c5 | 2 | 微积分学教程（菲赫金哥尔茨） 套2 | 教程2：微积分学教程（菲赫金哥尔茨） | {title: 微积分学教程, authors: [菲赫金哥尔茨], version: {}} |
| kn_ad4d78ac7cd65bc0116fad84a5e5e77a | 3 | 数学分析（陈纪修） 套3 | 教程3：数学分析（陈纪修） | {title: 数学分析（陈纪修）, authors: [陈纪修], version: {}} |

说明：
- 套1 存在中英两版 textbook 书籍（数学分析原理 zh / Principles of Mathematical Analysis en），
  命名取**中文套优先 zh 语言书籍**（数学分析原理 / Rudin）。
- 套3 书籍 title 已含「（陈纪修）」后缀，`tutorial_name` 检测同名作者后缀去重，
  避免「教程3：数学分析（陈纪修）（陈纪修）」。
- `before.txt` 的 name/textbook_ref 取自 2026-08-20 修正前巡检快照；`updated_at` 以
  `completed_at` 近似（修正前最后一次已知变更），如需精确值可从 MySQL binlog 追溯。
- 书籍数据未触碰（与 QED-034 一致，磁盘零触碰）。

## 证据文件

- `before.txt`：修正前三行全行 dump（knowledge + 书籍，name/textbook_ref 为修正前真实值）。
- `after.txt`：修正后三行全行 dump（2026-08-20 19:36 执行后状态）。

## 执行

一次性脚本（临时，未入库）以 SQLAlchemy + 原生 SQL 执行：读取 → 校验 → UPDATE → commit →
dump 归档；随后 8901 API 冒烟核验（GET /api/v1/knowledge 返回新 name）。
