# qt_resources 退役归档（QED-030）

状态：Historical
最后更新：2026-08-14
日期：2026-08-14

本目录保存 qt_resources 旧表退役（QED-030，0005 迁移 drop）的证据快照，
以及 12 册明细对照表清理（15 行历史 selection 删除）的备份。均为只读证据，
不得作为当前操作依据；当前事实入口是[文档索引](../index.md)。

## 文件

- `qt_resources_full_backup.json`：drop 前 qt_resources 全量 29 行（含 catalog_ref/source/状态时间戳）。
- `three_tables_snapshot.json`：退役时三表现状（qt_selections 4 行 / qt_downloads 12 行 / qt_sources 16 行）。
- `alembic_version.txt`：退役前 alembic 版本（0004_download_intro）。
- `selections_deleted_backup.json`：12 册明细清理删除的 15 行历史 selection（superseded×5、
  rejected×1、polya×1、02/06 课程候选×8）全量字段备份。

## 一次性脚本归档说明（2026-08-13 用户裁决：删除并归档证据）

以下一次性脚本执行完成后随 qt_resources 退役一并删除（数据已落三表/表2 intro）：

- `application/regroup_selections.py`：教程级归并（三个教程 tut_* + vol 规范化，2026-08-13 已执行）。
- `application/data_fix.py`：手动下载 4 册 manual 渠道标注 + 乱码 note 清理（已执行：qt_sources 16 行）。
- `application/intros.py` + `cli catalog intro`：表2 简介生成（已执行：qt_downloads.intro 12 条）。
- `application/migrate_three_table.py`：0003 存量迁移脚本（e764214 已执行，可从 Git 历史恢复）。

regroup/data_fix/intros 三个脚本及对应测试一直未纳入版本控制，删除后不可从 Git 恢复；
如需复现，依据本文档与 `qt_resources_full_backup.json`/`three_tables_snapshot.json` 证据重建。